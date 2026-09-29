from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LoginSession, User
from app.security import decode_token

DbSession = Annotated[Session, Depends(get_db)]
bearer = HTTPBearer(auto_error=False)


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_login_session(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> LoginSession:
    if credentials is None:
        raise authentication_error()
    try:
        claims = decode_token(credentials.credentials, "access")
    except jwt.InvalidTokenError:
        raise authentication_error() from None
    session = db.get(LoginSession, UUID(claims["sid"]))
    if (
        session is None
        or session.expires_at <= datetime.now(timezone.utc)
        or str(session.user_id) != claims["sub"]
    ):
        raise authentication_error()
    return session


CurrentSession = Annotated[LoginSession, Depends(get_login_session)]


def get_current_user(session: CurrentSession) -> User:
    return session.user


CurrentUser = Annotated[User, Depends(get_current_user)]
