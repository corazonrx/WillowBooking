#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../backend"

python -m alembic upgrade head
python -m app.seed
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
