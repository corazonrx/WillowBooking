import os
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy import make_url, text

BACKEND = Path(__file__).resolve().parents[1]
base_url = make_url(os.environ.get("DATABASE_URL") or dotenv_values(BACKEND / ".env")["DATABASE_URL"])
test_database_name = "hotel_test_" + uuid4().hex
test_url = base_url.set(database=test_database_name)
os.environ["DATABASE_URL"] = test_url.render_as_string(hide_password=False)
os.environ["JWT_SECRET_KEY"] = token_urlsafe(48)

from app.database import SessionLocal, engine
from app.main import app
from app.seed import seed_data
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def test_database():
    admin_url = base_url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test_database_name)))
    try:
        command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
        yield
    finally:
        engine.dispose()
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(test_database_name)))


@pytest.fixture(autouse=True)
def clean_database(test_database):
    assert engine.url.database == test_database_name
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE bookings, login_sessions, rooms, room_types, users RESTART IDENTITY CASCADE"))
    seed_data()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def account(client):
    def create(email="guest@example.com"):
        data = {"email": email, "password": "Test-password-123", "full_name": "Test Guest"}
        response = client.post("/auth/register", json=data)
        assert response.status_code == 201, response.text
        login = client.post("/auth/login", json={"email": email, "password": data["password"]})
        assert login.status_code == 200, login.text
        return {"Authorization": "Bearer " + login.json()["access_token"]}
    return create
