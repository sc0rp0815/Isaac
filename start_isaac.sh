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

echo "[Isaac] Starte isaac_core.py (Kernel + WS + HTTP in einem Prozess) ..."
nohup python isaac_core.py > isaac.out 2>&1 &
CORE_PID=$!
echo "[Isaac] Core PID: $CORE_PID"

echo "$CORE_PID" > runtime/isaac.pid
# Kompatibilitätsdatei für bestehende Stop-/Status-Skripte
printf '%s
' "$CORE_PID" > runtime/monitor.pid

sleep 2

echo "[Isaac] Letzte Core-Logs:"
tail -n 40 isaac.out || true

echo "[Isaac] Dashboard: http://localhost:${MONITOR_HTTP_PORT:-8766}"
echo "[Isaac] WebSocket: ws://localhost:${MONITOR_PORT:-8765}"
