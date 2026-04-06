#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ISAAC_DIR="${1:-/root/Isaac/isaac}"
cd "$ISAAC_DIR"

mkdir -p logs runtime workspace
[ -f .env ] || cp .env.example .env

export PYTHONUNBUFFERED=1
export ISAAC_RUNTIME_ENV=termux

if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock || true
fi

echo "[Isaac] Startpfad: $ISAAC_DIR"
echo "[Isaac] Verwende Python: $(command -v python3 || true)"
echo "[Isaac] Starte isaac_core.py ..."
python3 isaac_core.py 2>&1 | tee -a logs/isaac.log
