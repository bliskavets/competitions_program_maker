#!/usr/bin/env bash
set -euo pipefail

# Apply database migrations, then launch the web server.
echo "Running database migrations..."
alembic upgrade head

echo "Starting Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
