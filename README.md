# Willow Hotel

Hotel reservation website built with FastAPI, PostgreSQL, SQLAlchemy, Alembic and Jinja2.

## Features

- JWT authentication with access and refresh tokens.
- Room availability by date and guest count.
- Automatic room assignment and price calculation.
- Reservation history and cancellation.
- Responsive interface and photo gallery.

## Requirements

- Python 3.14
- Docker Compose

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
```

Set matching PostgreSQL credentials in `POSTGRES_PASSWORD` and `DATABASE_URL`. Generate a signing key and set `JWT_SECRET_KEY` in `backend/.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

```bash
docker compose up -d --wait
cd backend
python -m alembic upgrade head
python -m app.seed
python -m uvicorn app.main:app --reload
```

- Website: http://127.0.0.1:8000/
- API documentation: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

## Structure

```text
backend/
  app/
  migrations/
  tests/
frontend/
  templates/
  static/
  tests/
compose.yaml
```

## Tests

From `backend`:

```bash
python -m pytest -q
python -m alembic check
```

Browser tests require Node.js, Google Chrome and Playwright:

```bash
cd frontend
npm install
cd ../backend
RUN_BROWSER_TESTS=1 python -m pytest tests/test_browser.py -q
```

Tests use a separate PostgreSQL database. The database user must have permission to create databases.
