#!/usr/bin/env bash
# Production entrypoint for the API container.
#
# 1. If RUN_MIGRATIONS is set to "1" (the default), run Alembic migrations
#    against DATABASE_URL using a synchronous psycopg-friendly URL.
# 2. Hand off (exec) to whatever CMD was passed (typically uvicorn).
#
# This script is safe to skip migrations (RUN_MIGRATIONS=0) when running
# multiple replicas — only one replica should hold the migration lock.
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
    echo "[entrypoint] Running Alembic migrations…"
    alembic upgrade head
    echo "[entrypoint] Migrations complete."
else
    echo "[entrypoint] RUN_MIGRATIONS=0 — skipping migrations."
fi

echo "[entrypoint] Starting: $*"
exec "$@"
