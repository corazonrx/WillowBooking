from datetime import datetime, timedelta, timezone
from secrets import compare_digest
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.dependencies import CurrentSession, CurrentUser, DbSession, authentication_error
from app.models import LoginSession, User
from app.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenRead, UserRead
from app.security import DUMMY_PASSWORD_HASH, decode_token, hash_token, issue_token_pair, password_hasher

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserRead, status_code=201)
def register(data: RegisterRequest, db: DbSession):
    user = User(
        email=data.email,
        full_name=data.full_name,
        password_hash=password_hasher.hash(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from None
    return user


@router.post("/login", response_model=TokenRead)
def login(data: LoginRequest, db: DbSession, response: Response):
    user = db.scalar(select(User).where(User.email == data.email))
    valid = password_hasher.verify(data.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not valid or user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    session = LoginSession(
        id=uuid4(),
        user_id=user.id,
        expires_at=(datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days)).replace(microsecond=0),
    )
    tokens = issue_token_pair(session)
    db.add(session)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return tokens


@router.post("/refresh", response_model=TokenRead)
def refresh(data: RefreshRequest, db: DbSession, response: Response):
    try:
        claims = decode_token(data.refresh_token, "refresh")
    except jwt.InvalidTokenError:
        raise authentication_error() from None
    # Lock the session so a refresh token can only be used once.
    session = db.scalar(select(LoginSession).where(LoginSession.id == UUID(claims["sid"])).with_for_update())
    if (
        session is None
        or session.expires_at <= datetime.now(timezone.utc)
        or str(session.user_id) != claims["sub"]
        or not compare_digest(session.refresh_token_hash, hash_token(data.refresh_token))
    ):
        raise authentication_error()
    tokens = issue_token_pair(session)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return tokens


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser):
    return user


@router.post("/logout", status_code=204)
def logout(session: CurrentSession, db: DbSession):
    # Use the same lock as refresh to make concurrent refresh/logout safe.
    locked_session = db.scalar(select(LoginSession).where(LoginSession.id == session.id).with_for_update())
    if locked_session is not None:
        db.delete(locked_session)
    db.commit()
    return Response(status_code=204)
