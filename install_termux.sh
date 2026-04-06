#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TARGET_DIR="${1:-/root/Isaac/isaac}"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[Isaac] Ziel: $TARGET_DIR"
mkdir -p "$TARGET_DIR"
cp -R "$SRC_DIR"/. "$TARGET_DIR"/

cd "$TARGET_DIR"
rm -rf __pycache__

if command -v pkg >/dev/null 2>&1; then
  pkg update -y || true
  pkg install -y python curl unzip git clang rust make libffi openssl || true
fi

python3 -m pip install --upgrade pip || true
python3 -m pip install -r requirements.txt

[ -f .env ] || cp .env.example .env
chmod +x start_termux.sh run_isaac.sh install_termux.sh install_alpine.sh

if grep -q '^ACTIVE_PROVIDER=ollama' .env 2>/dev/null; then
  echo "[Isaac] Hinweis: Für ACTIVE_PROVIDER=ollama muss Ollama separat laufen."
fi

echo "[Isaac] Termux-Installation abgeschlossen."
echo "Start:  cd $TARGET_DIR && bash run_isaac.sh"
