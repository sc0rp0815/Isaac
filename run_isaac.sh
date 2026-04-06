#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -x /data/data/com.termux/files/usr/bin/bash ] && command -v termux-wake-lock >/dev/null 2>&1; then
  exec "$SCRIPT_DIR/start_termux.sh" "$SCRIPT_DIR"
else
  exec "$SCRIPT_DIR/start_alpine.sh" "$SCRIPT_DIR"
fi
