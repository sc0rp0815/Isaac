#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
TARGET="${1:-.}"
cp "$(dirname "$0")/relay.py" "$TARGET/relay.py"
cp "$(dirname "$0")/regelwerk.py" "$TARGET/regelwerk.py"
cp "$(dirname "$0")/background_loop.py" "$TARGET/background_loop.py"
echo "[Isaac] cumulative stability fix applied to $TARGET"
