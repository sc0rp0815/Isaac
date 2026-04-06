#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p logs runtime workspace
if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
else
  PY=$(command -v python3)
fi
echo "[Isaac] Dashboard + Core start in $SCRIPT_DIR"
nohup "$PY" monitor_server.py >> logs/monitor_server.log 2>&1 &
MON_PID=$!
echo "$MON_PID" > runtime/monitor_server.pid
nohup "$PY" isaac_core.py >> logs/isaac.log 2>&1 &
CORE_PID=$!
echo "$CORE_PID" > runtime/isaac_core.pid
echo "monitor_server PID=$MON_PID"
echo "isaac_core PID=$CORE_PID"
echo "Dashboard URL: http://localhost:8766/"
