from datetime import datetime, timedelta
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, HOTEL_ZONE, Settings
from app.database import SessionLocal, engine
from app.models import Room


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_render_database_url_preserves_credentials_and_options(scheme):
    suffix = "guest:p%40ss%2Fword@db.internal:5432/hotel?sslmode=require"
    settings = Settings(database_url=f"{scheme}://{suffix}", jwt_secret_key="a" * 43)
    assert settings.database_url == f"postgresql+psycopg://{suffix}"


def test_health_returns_unavailable_when_database_fails(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("Connection failed"))

    monkeypatch.setattr(Session, "execute", unavailable)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}


def test_render_start_migrates_empty_database_and_preserves_bookings(client, account, tmp_path):
    command.downgrade(Config(str(BACKEND_DIR / "alembic.ini")), "base")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ | {
        "DATABASE_URL": engine.url.set(drivername="postgresql").render_as_string(hide_password=False),
        "PORT": str(port),
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
    }
    script = BACKEND_DIR.parent / "scripts/start-render.sh"
    with (tmp_path / "render-start.log").open("w") as log, httpx.Client(base_url=base_url, timeout=2) as web:
        for attempt in range(2):
            server = subprocess.Popen(["bash", str(script)], cwd=tmp_path, env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        pytest.fail("Render startup failed; inspect render-start.log")
                    try:
                        if web.get("/api/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail("Render startup timed out; inspect render-start.log")

                assert web.get("/").status_code == 200
                assert web.get("/static/css/style.css").status_code == 200
                assert web.get("/static/images/lounge.jpg").status_code == 200
                assert len(web.get("/room-types").json()) == 3
                with SessionLocal() as db:
                    assert db.scalar(select(func.count()).select_from(Room)) == 6

                if attempt == 0:
                    headers = account()
                    today = datetime.now(HOTEL_ZONE).date()
                    booking = web.post("/bookings", headers=headers, json={
                        "room_type_id": 1,
                        "check_in": (today + timedelta(days=10)).isoformat(),
                        "check_out": (today + timedelta(days=12)).isoformat(),
                        "arrival_window": "14:00-16:00",
                        "guests": 2,
                    })
                    assert booking.status_code == 201, booking.text
                    booking_id = booking.json()["id"]
                else:
                    bookings = web.get("/bookings", headers=headers)
                    assert bookings.status_code == 200
                    assert [item["id"] for item in bookings.json()] == [booking_id]
            finally:
                server.terminate()
                server.wait(timeout=10)
