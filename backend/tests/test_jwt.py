from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from alembic import command
from alembic.config import Config

from app.config import BACKEND_DIR, settings
from app.database import SessionLocal, engine
from app.main import app
from app.models import LoginSession
from app.security import JWT_ALGORITHM, decode_token, hash_token


@pytest.fixture
def tokens(client, account):
    account()
    response = client.post("/auth/login", json={"email": "guest@example.com", "password": "Test-password-123"})
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def bearer(token):
    return {"Authorization": "Bearer " + token}


def sign(claims, key=None, algorithm=JWT_ALGORITHM):
    return jwt.encode(claims, key or settings.jwt_secret_key.get_secret_value(), algorithm=algorithm)


def test_jwt_claims_and_storage(client, tokens):
    access = decode_token(tokens["access_token"], "access")
    refresh = decode_token(tokens["refresh_token"], "refresh")
    assert access["sid"] == refresh["sid"]
    assert access["sub"] == refresh["sub"]
    assert access["jti"] != refresh["jti"]
    assert access["exp"] - access["iat"] == 15 * 60
    assert refresh["exp"] - refresh["iat"] == 7 * 24 * 3600
    assert access["exp"] == int(datetime.fromisoformat(tokens["expires_at"].replace("Z", "+00:00")).timestamp())
    with SessionLocal() as db:
        session = db.get(LoginSession, UUID(refresh["sid"]))
        assert session.refresh_token_hash == hash_token(tokens["refresh_token"])
        assert session.refresh_token_hash not in tokens.values()
    assert client.get("/auth/me", headers=bearer(tokens["access_token"])).status_code == 200


def test_refresh_rotates_and_rejects_replay(client, tokens):
    response = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    new = response.json()
    assert new["access_token"] != tokens["access_token"]
    assert new["refresh_token"] != tokens["refresh_token"]
    assert new["refresh_expires_at"] == tokens["refresh_expires_at"]
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.get("/auth/me", headers=bearer(new["access_token"])).status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 200


def test_token_types_are_not_interchangeable(client, tokens):
    assert client.get("/auth/me", headers=bearer(tokens["refresh_token"])).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]}).status_code == 401


@pytest.mark.parametrize("patch", [
    {"exp": 1}, {"iat": 4102444800}, {"iss": "other-app"}, {"aud": "other-api"},
    {"sid": "not-a-uuid"}, {"sid": None}, {"sid": str(uuid4())},
    {"sub": "999999"}, {"sub": []}, {"jti": "not-a-uuid"},
])
def test_invalid_access_claims(client, tokens, patch):
    claims = decode_token(tokens["access_token"], "access") | patch
    response = client.get("/auth/me", headers=bearer(sign(claims)))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("missing", ["sub", "sid", "jti", "token_type", "iat", "exp", "iss", "aud"])
def test_required_claims(client, tokens, missing):
    claims = decode_token(tokens["access_token"], "access")
    del claims[missing]
    assert client.get("/auth/me", headers=bearer(sign(claims))).status_code == 401


def test_signature_algorithm_and_tampering(client, tokens):
    claims = decode_token(tokens["access_token"], "access")
    invalid = [
        sign(claims, key="a-different-secret-with-at-least-43-characters"),
        sign(claims, algorithm="HS384"),
        jwt.encode(claims, key=None, algorithm="none"),
        "old-opaque-session-token",
    ]
    modified_payload = sign(claims | {"sub": "123"}).split(".")
    modified_payload[2] = tokens["access_token"].split(".")[2]
    invalid.append(".".join(modified_payload))
    for token in invalid:
        assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_refresh_expiry_revocation_and_bad_tokens(client, tokens):
    claims = decode_token(tokens["refresh_token"], "refresh")
    for token in (sign(claims | {"exp": 1}), "invalid", sign(claims | {"sub": "123"})):
        assert client.post("/auth/refresh", json={"refresh_token": token}).status_code == 401
    with SessionLocal.begin() as db:
        db.get(LoginSession, UUID(claims["sid"])).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_refresh_after_access_expiry(client, tokens):
    claims = decode_token(tokens["access_token"], "access")
    assert client.get("/auth/me", headers=bearer(sign(claims | {"exp": 1}))).status_code == 401
    response = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    assert client.get("/auth/me", headers=bearer(response.json()["access_token"])).status_code == 200


def test_logout_revokes_rotated_session_only(client, tokens):
    separate = client.post("/auth/login", json={"email": "guest@example.com", "password": "Test-password-123"}).json()
    rotated = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
    assert client.post("/auth/logout", headers=bearer(rotated["access_token"])).status_code == 204
    for pair in (tokens, rotated):
        assert client.get("/auth/me", headers=bearer(pair["access_token"])).status_code == 401
        assert client.post("/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code == 401
    assert client.get("/auth/me", headers=bearer(separate["access_token"])).status_code == 200


def test_parallel_refresh_uses_token_once(tokens):
    barrier = Barrier(2)

    def refresh():
        with TestClient(app) as client:
            barrier.wait(timeout=10)
            return client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: refresh(), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 401]
    winner = next(response.json() for response in responses if response.status_code == 200)
    with TestClient(app) as client:
        assert client.post("/auth/refresh", json={"refresh_token": winner["refresh_token"]}).status_code == 200


def test_migration_preserves_existing_rows(tokens):
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    with engine.connect() as connection:
        before = connection.execute(text("SELECT refresh_token_hash, user_id, expires_at FROM login_sessions ORDER BY refresh_token_hash")).all()
    command.downgrade(config, "415bcb3c659e")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        after = connection.execute(text("SELECT refresh_token_hash, user_id, expires_at FROM login_sessions ORDER BY refresh_token_hash")).all()
    assert after == before
