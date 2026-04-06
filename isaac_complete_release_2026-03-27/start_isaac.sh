#!/bin/sh
set -eu

cd /root/Isaac/isaac

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

OLLAMA_URL="${OLLAMA_HOST:-http://127.0.0.1:11434}"

echo "┌──────────────────────────────┐"
echo "│      Isaac - Startup         │"
echo "└──────────────────────────────┘"
echo "[Isaac] Nutze externes Ollama: $OLLAMA_URL"

if ! curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  echo "[Isaac] Fehler: externes Ollama nicht erreichbar unter $OLLAMA_URL"
  echo "[Isaac] Starte Ollama in normalem Termux mit: ollama serve"
  exit 1
fi

echo "[Isaac] Externes Ollama erreichbar ✓"

mkdir -p logs runtime workspace

if [ -d .venv ]; then
  . .venv/bin/activate
fi

echo "[Isaac] Starte monitor_server.py ..."
nohup python monitor_server.py > monitor.out 2>&1 &
MON_PID=$!
echo "[Isaac] Monitor PID: $MON_PID"

echo "[Isaac] Starte isaac_core.py ..."
nohup python isaac_core.py > isaac.out 2>&1 &
CORE_PID=$!
echo "[Isaac] Core PID: $CORE_PID"

echo "$MON_PID" > runtime/monitor.pid
echo "$CORE_PID" > runtime/isaac.pid

sleep 2

echo "[Isaac] Letzte Core-Logs:"
tail -n 20 isaac.out || true

echo "[Isaac] Letzte Monitor-Logs:"
tail -n 20 monitor.out || true

echo "[Isaac] Dashboard: http://localhost:${DASHBOARD_PORT:-8766}"
echo "[Isaac] WebSocket: ws://localhost:${MONITOR_PORT:-8765}"
