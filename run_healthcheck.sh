#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$ROOT_DIR/package}"
if [ -x "$TARGET_DIR/.venv/bin/python" ]; then
  PY="$TARGET_DIR/.venv/bin/python"
else
  PY="$(command -v python3)"
fi
cd "$TARGET_DIR"
exec "$PY" healthcheck_isaac.py
