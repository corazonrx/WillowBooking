from sqlalchemy import select

from app.database import SessionLocal
from app.models import Room, RoomType

CATALOG = [
    ("Classic", 2, 10000, "A comfortable room for up to two guests.", ["101", "102"]),
    ("Deluxe", 2, 16000, "A spacious room for up to two guests.", ["201", "202"]),
    ("Family", 4, 22000, "A family room for up to four guests.", ["301", "302"]),
]


def seed_data():
    with SessionLocal.begin() as db:
        for name, capacity, price, description, numbers in CATALOG:
            room_type = db.scalar(select(RoomType).where(RoomType.name == name))
            if room_type is None:
                room_type = RoomType(name=name, capacity=capacity, price_per_night=price, description=description)
                db.add(room_type)
                db.flush()
            for number in numbers:
                if db.scalar(select(Room).where(Room.number == number)) is None:
                    db.add(Room(number=number, room_type_id=room_type.id))


if __name__ == "__main__":
    seed_data()
    print("Room catalog is ready.")
