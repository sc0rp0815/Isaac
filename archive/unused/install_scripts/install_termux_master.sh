#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$HOME/Isaac/isaac}"

pkg update -y || true
pkg install -y python clang make rust unzip || true
mkdir -p "$TARGET_DIR"
if [ ! -d "$TARGET_DIR/.venv" ]; then
  python3 -m venv "$TARGET_DIR/.venv"
fi
. "$TARGET_DIR/.venv/bin/activate"
python -m pip install --upgrade pip wheel setuptools
bash "$SCRIPT_DIR/install_master.sh" "$TARGET_DIR"
