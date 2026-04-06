#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$HOME/Isaac/isaac}"

echo "[Update] Reinstalling Isaac master bundle into: $TARGET_DIR"
bash "$SCRIPT_DIR/install_master.sh" "$TARGET_DIR"
echo "[Update] Done."
