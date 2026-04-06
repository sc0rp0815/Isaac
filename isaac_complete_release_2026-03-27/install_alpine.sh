#!/bin/sh
set -eu

TARGET_DIR="${1:-/root/Isaac/isaac}"
SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

echo "[Isaac] Ziel: $TARGET_DIR"
mkdir -p "$TARGET_DIR"
cp -R "$SRC_DIR"/. "$TARGET_DIR"/

cd "$TARGET_DIR"
rm -rf __pycache__

if command -v apk >/dev/null 2>&1; then
  apk add --no-cache python3 py3-pip curl unzip git build-base libffi-dev openssl-dev || true
fi

python3 -m pip install --break-system-packages --upgrade pip || true
python3 -m pip install --break-system-packages -r requirements.txt || python3 -m pip install -r requirements.txt

[ -f .env ] || cp .env.example .env
chmod +x start_alpine.sh run_isaac.sh install_termux.sh install_alpine.sh

if grep -q '^ACTIVE_PROVIDER=ollama' .env 2>/dev/null; then
  echo "[Isaac] Hinweis: Für ACTIVE_PROVIDER=ollama muss Ollama separat laufen."
fi

echo "[Isaac] Alpine-Installation abgeschlossen."
echo "Start:  cd $TARGET_DIR && sh run_isaac.sh"
