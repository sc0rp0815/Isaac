#!/bin/sh
set -eu

ISAAC_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
cd "$ISAAC_DIR"

mkdir -p logs runtime workspace data
[ -f .env ] || cp .env.example .env

export PYTHONUNBUFFERED=1
export ISAAC_RUNTIME_ENV=alpine
export ISAAC_DISABLE_VECTOR_MEMORY="${ISAAC_DISABLE_VECTOR_MEMORY:-1}"
export MONITOR_PORT="${MONITOR_PORT:-8765}"
export DASHBOARD_PORT="${DASHBOARD_PORT:-8766}"
export MONITOR_HTTP_PORT="${MONITOR_HTTP_PORT:-8766}"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="python3"
fi

echo "[Isaac] Startpfad: $ISAAC_DIR"
echo "[Isaac] Python: $($PY --version 2>&1 || true)"
echo "[Isaac] Dashboard: http://127.0.0.1:${MONITOR_HTTP_PORT}"
echo "[Isaac] Starte isaac_core.py …"
exec "$PY" isaac_core.py 2>&1 | tee -a logs/isaac.log
