from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.dependencies import DbSession
from app.models import RoomType
from app.schemas import AvailabilityRead, RoomTypeRead, StayRequest
from app.services import free_rooms_query

router = APIRouter(tags=["Rooms"])


@router.get("/room-types", response_model=list[RoomTypeRead])
def get_room_types(db: DbSession):
    return db.scalars(select(RoomType).order_by(RoomType.id)).all()


@router.get("/room-types/{room_type_id}", response_model=RoomTypeRead)
def get_room_type(room_type_id: int, db: DbSession):
    room_type = db.get(RoomType, room_type_id)
    if room_type is None:
        raise HTTPException(status_code=404, detail="Room type not found")
    return room_type


@router.get("/availability", response_model=list[AvailabilityRead])
def get_availability(stay: Annotated[StayRequest, Query()], db: DbSession):
    room_types = db.scalars(select(RoomType).where(RoomType.capacity >= stay.guests).order_by(RoomType.id))
    nights = (stay.check_out - stay.check_in).days
    return [
        AvailabilityRead(
            room_type=RoomTypeRead.model_validate(room_type),
            available_rooms=len(db.scalars(free_rooms_query(room_type.id, stay.check_in, stay.check_out)).all()),
            nights=nights,
            total_price=nights * room_type.price_per_night,
        )
        for room_type in room_types
    ]
