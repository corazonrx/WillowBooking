from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship()


class RoomType(Base):
    __tablename__ = "room_types"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="positive_capacity"),
        CheckConstraint("price_per_night > 0", name="positive_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    capacity: Mapped[int]
    description: Mapped[str] = mapped_column(String(500))
    price_per_night: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), default="PLN")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(10), unique=True)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), index=True)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("check_out > check_in", name="valid_stay_dates"),
        CheckConstraint("guests > 0", name="positive_guests"),
        CheckConstraint("total_price > 0", name="positive_total"),
        CheckConstraint("status IN ('confirmed', 'cancelled')", name="valid_status"),
        ExcludeConstraint(
            ("room_id", "="),
            (func.daterange(text("check_in"), text("check_out"), "[)"), "&&"),
            where=text("status = 'confirmed'"),
            name="no_overlapping_bookings",
            using="gist",
        ),
        ExcludeConstraint(
            ("user_id", "="),
            (func.daterange(text("check_in"), text("check_out"), "[)"), "&&"),
            where=text("status = 'confirmed'"),
            name="no_overlapping_user_bookings",
            using="gist",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    check_in: Mapped[date]
    check_out: Mapped[date]
    arrival_window: Mapped[str] = mapped_column(String(11))
    guests: Mapped[int]
    total_price: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    room: Mapped[Room] = relationship(lazy="joined")
