from datetime import date

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Booking, Room, RoomType, User
from app.schemas import BookingCreate


def free_rooms_query(room_type_id: int, check_in: date, check_out: date):
    overlap = exists().where(
        Booking.room_id == Room.id,
        Booking.status == "confirmed",
        Booking.check_in < check_out,
        Booking.check_out > check_in,
    )
    return select(Room).where(Room.room_type_id == room_type_id, ~overlap).order_by(Room.number)


def create_booking(db: Session, user: User, data: BookingCreate) -> Booking:
    # Lock the account first, including reservations across different categories.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    overlapping_stay = db.scalar(select(Booking.id).where(
        Booking.user_id == user.id,
        Booking.status == "confirmed",
        Booking.check_in < data.check_out,
        Booking.check_out > data.check_in,
    ).limit(1))
    if overlapping_stay is not None:
        raise HTTPException(status_code=409, detail="You already have a reservation for these dates")

    # Serialize reservations in this category until the transaction commits.
    room_type = db.scalar(select(RoomType).where(RoomType.id == data.room_type_id).with_for_update())
    if room_type is None:
        raise HTTPException(status_code=404, detail="Room type not found")
    if data.guests > room_type.capacity:
        raise HTTPException(status_code=422, detail="Too many guests for this room type")
    room = db.scalar(free_rooms_query(room_type.id, data.check_in, data.check_out).limit(1))
    if room is None:
        raise HTTPException(status_code=409, detail="No rooms available for these dates")

    nights = (data.check_out - data.check_in).days
    booking = Booking(
        user_id=user.id,
        room_id=room.id,
        check_in=data.check_in,
        check_out=data.check_out,
        arrival_window=data.arrival_window,
        guests=data.guests,
        total_price=nights * room_type.price_per_night,
        currency=room_type.currency,
    )
    db.add(booking)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23P01":
            if exc.orig.diag.constraint_name == "no_overlapping_user_bookings":
                raise HTTPException(status_code=409, detail="You already have a reservation for these dates") from None
            raise HTTPException(status_code=409, detail="No rooms available for these dates") from None
        raise
    db.refresh(booking)
    return booking
