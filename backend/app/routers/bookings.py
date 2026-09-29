from datetime import datetime, time
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.config import HOTEL_ZONE
from app.dependencies import CurrentUser, DbSession
from app.models import Booking
from app.schemas import BookingCreate, BookingRead
from app.services import create_booking

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.post("", response_model=BookingRead, status_code=201)
def book_room(data: BookingCreate, db: DbSession, user: CurrentUser):
    return create_booking(db, user, data)


@router.get("", response_model=list[BookingRead])
def list_bookings(db: DbSession, user: CurrentUser):
    return db.scalars(select(Booking).where(Booking.user_id == user.id).order_by(Booking.created_at.desc())).all()


@router.get("/{booking_id}", response_model=BookingRead)
def get_booking(booking_id: UUID, db: DbSession, user: CurrentUser):
    booking = db.scalar(select(Booking).where(Booking.id == booking_id, Booking.user_id == user.id))
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingRead)
def cancel_booking(booking_id: UUID, db: DbSession, user: CurrentUser):
    booking = db.scalar(
        select(Booking).where(Booking.id == booking_id, Booking.user_id == user.id).with_for_update(of=Booking)
    )
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status == "cancelled":
        return booking
    arrival_start = time.fromisoformat(booking.arrival_window.split("-")[0])
    if datetime.combine(booking.check_in, arrival_start, HOTEL_ZONE) <= datetime.now(HOTEL_ZONE):
        raise HTTPException(status_code=409, detail="The stay has already started")
    booking.status = "cancelled"
    db.commit()
    return booking
