from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Literal
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.config import settings
from app.models import LoginSession
from app.schemas import TokenRead

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "hotel-booking"
JWT_AUDIENCE = "hotel-booking-api"
password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash("dummy-password-for-timing")


def hash_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def encode_token(session: LoginSession, token_type: str, expires_at: datetime) -> str:
    return jwt.encode(
        {
            "sub": str(session.user_id),
            "sid": str(session.id),
            "jti": str(uuid4()),
            "token_type": token_type,
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int(expires_at.timestamp()),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> dict:
    claims = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
        options={"require": ["sub", "sid", "jti", "token_type", "iat", "exp", "iss", "aud"]},
    )
    if claims["token_type"] != expected_type:
        raise jwt.InvalidTokenError("Invalid token type")
    if not isinstance(claims["sub"], str) or not claims["sub"].isdecimal():
        raise jwt.InvalidTokenError("Invalid subject")
    if type(claims["exp"]) is not int or type(claims["iat"]) is not int:
        raise jwt.InvalidTokenError("Invalid token timestamps")
    try:
        UUID(claims["sid"])
        UUID(claims["jti"])
    except (ValueError, TypeError, AttributeError):
        raise jwt.InvalidTokenError("Invalid token identifier") from None
    return claims


def issue_token_pair(session: LoginSession) -> TokenRead:
    expires_at = min(
        datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes),
        session.expires_at,
    ).replace(microsecond=0)
    refresh_token = encode_token(session, "refresh", session.expires_at)
    session.refresh_token_hash = hash_token(refresh_token)
    return TokenRead(
        access_token=encode_token(session, "access", expires_at),
        refresh_token=refresh_token,
        expires_at=expires_at,
        refresh_expires_at=session.expires_at,
    )
