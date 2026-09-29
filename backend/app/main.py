from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import BACKEND_DIR, settings
from app.dependencies import DbSession
from app.routers import auth, bookings, rooms
from app.schemas import ARRIVAL_WINDOWS

app = FastAPI(title="Hotel Booking API", version="1.0.0")
app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(bookings.router)
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
templates = Jinja2Templates(directory=FRONTEND_DIR / "templates")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/health", tags=["Hotel"])
def health(db: DbSession):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database is unavailable") from None
    return {"message": "Hotel is running"}


@app.get("/hotel", tags=["Hotel"])
def get_hotel():
    return {
        "name": "Willow Hotel",
        "timezone": settings.hotel_timezone,
        "checkout_time": "11:00",
        "arrival_windows": ARRIVAL_WINDOWS,
        "max_stay_nights": 30,
        "currency": "PLN",
        "price_unit": "grosz",
    }
