#!/bin/sh
set -eu

APP_ROOT="/app"
BUNDLED_DB_PATH="${BUNDLED_DB_PATH:-$APP_ROOT/venture_metrics_agent/data/processed/venture_metrics.db}"
DB_PATH="${DB_PATH:-$APP_ROOT/venture_metrics_agent/data/processed/venture_metrics.db}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

DB_DIR=$(dirname "$DB_PATH")
mkdir -p "$DB_DIR"

if [ ! -f "$DB_PATH" ] && [ -f "$BUNDLED_DB_PATH" ]; then
  cp "$BUNDLED_DB_PATH" "$DB_PATH"
fi

echo "Starting Venture Metrics server on ${HOST}:${PORT} with DB_PATH=${DB_PATH}"
exec python scripts/serve_agent.py --host "$HOST" --port "$PORT" --db "$DB_PATH"
