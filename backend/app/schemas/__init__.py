from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.config import HOTEL_ZONE

ArrivalWindow = Literal["14:00-16:00", "16:00-18:00", "18:00-20:00", "20:00-22:00"]
ARRIVAL_WINDOWS = ["14:00-16:00", "16:00-18:00", "18:00-20:00", "20:00-22:00"]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(RequestModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class RegisterRequest(LoginRequest):
    full_name: str = Field(min_length=1, max_length=100)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full name must not be blank")
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str


class TokenRead(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime
    refresh_expires_at: datetime


class RefreshRequest(RequestModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class RoomTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    capacity: int
    description: str
    price_per_night: int
    currency: str


class StayRequest(RequestModel):
    check_in: date
    check_out: date
    guests: int = Field(ge=1, le=4, default=1)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.check_in < datetime.now(HOTEL_ZONE).date():
            raise ValueError("Check-in must not be in the past")
        nights = (self.check_out - self.check_in).days
        if not 1 <= nights <= 30:
            raise ValueError("A stay must be between 1 and 30 nights")
        return self


class BookingCreate(StayRequest):
    room_type_id: int = Field(gt=0)
    arrival_window: ArrivalWindow

    @model_validator(mode="after")
    def validate_arrival(self):
        end = time.fromisoformat(self.arrival_window.split("-")[1])
        if datetime.combine(self.check_in, end, HOTEL_ZONE) <= datetime.now(HOTEL_ZONE):
            raise ValueError("The arrival window has already ended")
        return self


class AvailabilityRead(BaseModel):
    room_type: RoomTypeRead
    available_rooms: int
    nights: int
    total_price: int


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    room_type_id: int


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    room: RoomRead
    check_in: date
    check_out: date
    checkout_time: time = time(11, 0)
    arrival_window: str
    guests: int
    total_price: int
    currency: str
    status: str
    created_at: datetime
