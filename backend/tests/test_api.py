from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import BACKEND_DIR, HOTEL_ZONE
from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, LoginSession, Room, RoomType, User
from app.security import decode_token
from app.seed import seed_data
from app import schemas


def stay(**changes):
    today = datetime.now(HOTEL_ZONE).date()
    data = {
        "room_type_id": 1,
        "check_in": (today + timedelta(days=10)).isoformat(),
        "check_out": (today + timedelta(days=12)).isoformat(),
        "arrival_window": "14:00-16:00",
        "guests": 2,
    }
    return data | changes


def test_public_catalog(client):
    assert client.get("/api/health").json() == {"message": "Hotel is running"}
    assert client.get("/hotel").json()["checkout_time"] == "11:00"
    assert [room["name"] for room in client.get("/room-types").json()] == ["Classic", "Deluxe", "Family"]
    assert client.get("/room-types/1").json()["capacity"] == 2
    assert client.get("/room-types/999").status_code == 404
    assert client.get("/room-types/abc").status_code == 422
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_register_login_logout(client, account):
    headers = account("Guest@example.com")
    profile = client.get("/auth/me", headers=headers)
    assert profile.json()["email"] == "guest@example.com"
    assert "password_hash" not in profile.json()
    token = headers["Authorization"].split()[1]
    with SessionLocal() as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith("$argon2")
        from uuid import UUID
        session = db.get(LoginSession, UUID(decode_token(token, "access")["sid"]))
        assert session is not None
        assert session.refresh_token_hash != token
    duplicate = client.post("/auth/register", json={"email": "guest@example.com", "password": "Test-password-123", "full_name": "Duplicate"})
    assert duplicate.status_code == 409
    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401


@pytest.mark.parametrize("email,password", [("guest@example.com", "wrong-password"), ("nobody@example.com", "wrong-password")])
def test_invalid_login(client, account, email, password):
    account()
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.parametrize("patch", [{"email": "invalid"}, {"password": "short"}, {"full_name": "  "}, {"is_admin": True}])
def test_invalid_registration(client, patch):
    data = {"email": "guest@example.com", "password": "Test-password-123", "full_name": "Guest"} | patch
    assert client.post("/auth/register", json=data).status_code == 422


def test_authentication_required_and_expiry(client, account):
    assert client.get("/bookings").status_code == 401
    assert client.post("/bookings", json=stay()).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
    headers = account()
    with SessionLocal.begin() as db:
        session = db.scalar(select(LoginSession))
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_booking_price_persistence_and_privacy(client, account):
    owner = account()
    other = account("other@example.com")
    response = client.post("/bookings", json=stay(), headers=owner)
    assert response.status_code == 201, response.text
    booking = response.json()
    assert booking["room"]["number"] == "101"
    assert booking["total_price"] == 20000
    assert booking["currency"] == "PLN"
    assert booking["checkout_time"] == "11:00:00"
    assert booking["status"] == "confirmed"
    assert client.get("/bookings/" + booking["id"], headers=owner).json() == booking
    assert len(client.get("/bookings", headers=owner).json()) == 1
    assert client.get("/bookings", headers=other).json() == []
    assert client.get("/bookings/" + booking["id"], headers=other).status_code == 404
    assert client.post("/bookings/" + booking["id"] + "/cancel", headers=other).status_code == 404


def test_availability_capacity_and_cancellation(client, account):
    headers = account()
    second_guest = account("second@example.com")
    third_guest = account("third@example.com")
    params = {key: value for key, value in stay().items() if key in ("check_in", "check_out", "guests")}
    availability = client.get("/availability", params=params)
    assert availability.status_code == 200, availability.text
    assert availability.json()[0]["available_rooms"] == 2
    ids = []
    for expected_number, guest in (("101", headers), ("102", second_guest)):
        response = client.post("/bookings", json=stay(), headers=guest)
        assert response.status_code == 201
        assert response.json()["room"]["number"] == expected_number
        ids.append(response.json()["id"])
    unavailable = client.post("/bookings", json=stay(), headers=third_guest)
    assert unavailable.status_code == 409
    assert unavailable.json()["detail"] == "No rooms available for these dates"
    assert client.get("/availability", params=params).json()[0]["available_rooms"] == 0
    for _ in range(2):
        response = client.post(f"/bookings/{ids[0]}/cancel", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
    assert client.get("/availability", params=params).json()[0]["available_rooms"] == 1
    assert client.post("/bookings", json=stay(), headers=headers).status_code == 201
    family = client.get("/availability", params=params | {"guests": 4}).json()
    assert [item["room_type"]["name"] for item in family] == ["Family"]


def test_adjacent_stays_can_reuse_room(client, account):
    headers = account()
    first = client.post("/bookings", json=stay(), headers=headers).json()
    checkout = datetime.fromisoformat(first["check_out"]).date() + timedelta(days=1)
    second = client.post("/bookings", json=stay(check_in=first["check_out"], check_out=checkout.isoformat()), headers=headers)
    assert second.status_code == 201
    assert second.json()["room"]["id"] == first["room"]["id"]


@pytest.mark.parametrize("patch", [
    {"guests": 0}, {"guests": 3}, {"guests": 5},
    {"arrival_window": "01:00-02:00"}, {"total_price": 1}, {"room_id": 1},
    {"check_in": "2000-01-01"}, {"check_out": "2000-01-01"},
    {"check_in": "invalid"},
])
def test_invalid_booking(client, account, patch):
    assert client.post("/bookings", json=stay(**patch), headers=account()).status_code == 422


def test_invalid_dates_for_booking_and_search(client, account):
    headers = account()
    data = stay()
    for checkout in (data["check_in"], (datetime.fromisoformat(data["check_in"]) + timedelta(days=31)).date().isoformat()):
        assert client.post("/bookings", json=data | {"check_out": checkout}, headers=headers).status_code == 422
        response = client.get("/availability", params={"check_in": data["check_in"], "check_out": checkout})
        assert response.status_code == 422
    assert client.post("/bookings", json=stay(room_type_id=999), headers=headers).status_code == 404


def test_started_stay_cannot_be_cancelled(client, account):
    headers = account()
    booking = client.post("/bookings", json=stay(), headers=headers).json()
    with SessionLocal.begin() as db:
        row = db.scalar(select(Booking))
        row.check_in = datetime.now(HOTEL_ZONE).date() - timedelta(days=2)
        row.check_out = row.check_in + timedelta(days=1)
    assert client.post(f"/bookings/{booking['id']}/cancel", headers=headers).status_code == 409


def test_same_day_arrival_window_boundary(client, account, monkeypatch):
    headers = account()
    today = datetime.now(HOTEL_ZONE).date()

    class Afternoon(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.combine(today, datetime.min.time(), HOTEL_ZONE).replace(hour=16)

    monkeypatch.setattr(schemas, "datetime", Afternoon)
    data = stay(check_in=today.isoformat(), check_out=(today + timedelta(days=1)).isoformat())
    assert client.post("/bookings", json=data, headers=headers).status_code == 422
    assert client.post("/bookings", json=data | {"arrival_window": "16:00-18:00"}, headers=headers).status_code == 201


def test_concurrent_booking_requests(client, account):
    guests = [account(f"guest{i}@example.com") for i in range(3)]
    barrier = Barrier(3)

    def reserve(headers):
        with TestClient(app) as parallel_client:
            barrier.wait(timeout=10)
            return parallel_client.post("/bookings", json=stay(), headers=headers)

    with ThreadPoolExecutor(max_workers=3) as executor:
        responses = list(executor.map(reserve, guests))
    assert sorted(response.status_code for response in responses) == [201, 201, 409]
    room_ids = [response.json()["room"]["id"] for response in responses if response.status_code == 201]
    assert len(set(room_ids)) == 2


def test_database_rejects_overlap_even_without_api(client, account):
    client.post("/bookings", json=stay(), headers=account())
    other_id = client.get("/auth/me", headers=account("other@example.com")).json()["id"]
    with SessionLocal() as db:
        existing = db.scalar(select(Booking))
        duplicate = Booking(
            user_id=other_id, room_id=existing.room_id,
            check_in=existing.check_in, check_out=existing.check_out,
            arrival_window=existing.arrival_window, guests=1,
            total_price=10000, currency="PLN",
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError) as error:
            db.commit()
        assert error.value.orig.sqlstate == "23P01"
        assert error.value.orig.diag.constraint_name == "no_overlapping_bookings"
        db.rollback()


@pytest.mark.parametrize("room_type_id", [1, 2, 3])
@pytest.mark.parametrize("start,end", [(10, 12), (9, 11), (11, 13), (9, 13), (10, 11)])
def test_account_cannot_reserve_overlapping_stays(client, account, room_type_id, start, end):
    headers = account()
    assert client.post("/bookings", json=stay(), headers=headers).status_code == 201
    today = datetime.now(HOTEL_ZONE).date()
    response = client.post("/bookings", json=stay(
        room_type_id=room_type_id,
        check_in=(today + timedelta(days=start)).isoformat(),
        check_out=(today + timedelta(days=end)).isoformat(),
    ), headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "You already have a reservation for these dates"
    assert len(client.get("/bookings", headers=headers).json()) == 1


@pytest.mark.parametrize("room_types", [(1, 1, 1), (1, 2, 3)])
def test_concurrent_reservations_for_one_account(client, account, room_types):
    headers = account()
    barrier = Barrier(3)

    def reserve(room_type_id):
        with TestClient(app) as parallel_client:
            barrier.wait(timeout=10)
            return parallel_client.post("/bookings", json=stay(room_type_id=room_type_id), headers=headers)

    with ThreadPoolExecutor(max_workers=3) as executor:
        responses = list(executor.map(reserve, room_types))
    assert sorted(response.status_code for response in responses) == [201, 409, 409]
    for response in responses:
        if response.status_code == 409:
            assert response.json()["detail"] == "You already have a reservation for these dates"
    assert len(client.get("/bookings", headers=headers).json()) == 1


def test_database_rejects_account_overlap_in_another_room(client, account):
    client.post("/bookings", json=stay(), headers=account())
    with SessionLocal() as db:
        existing = db.scalar(select(Booking))
        other_room = db.scalar(select(Room).where(Room.room_type_id == 2))
        db.add(Booking(
            user_id=existing.user_id, room_id=other_room.id,
            check_in=existing.check_in, check_out=existing.check_out,
            arrival_window=existing.arrival_window, guests=1,
            total_price=10000, currency="PLN",
        ))
        with pytest.raises(IntegrityError) as error:
            db.commit()
        assert error.value.orig.sqlstate == "23P01"
        assert error.value.orig.diag.constraint_name == "no_overlapping_user_bookings"
        db.rollback()


def test_seed_is_repeatable():
    seed_data()
    seed_data()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RoomType)) == 3
        assert db.scalar(select(func.count()).select_from(Room)) == 6


def test_migration_round_trip():
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)
    seed_data()
