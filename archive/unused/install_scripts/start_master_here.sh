#!/usr/bin/env bash
set -euo pipefail
TARGET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/package" && pwd)"
cd "$TARGET_DIR"
if [ -d .venv ] && [ -x .venv/bin/python ]; then
  exec .venv/bin/python isaac_core.py
else
  exec python3 isaac_core.py
fi
