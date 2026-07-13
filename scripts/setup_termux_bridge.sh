#!/usr/bin/env bash
# Termux-Brücke für Isaac S8-Linux-Chroot einrichten.
# In Termux ausführen: bash /pfad/zu/isaac/scripts/setup_termux_bridge.sh
set -euo pipefail

ISAAC_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
TERMUX_HOME="${HOME:-/data/data/com.termux/files/home}"
BRIDGE_DIR="$TERMUX_HOME/.isaac/bridge"
ISAAC_DATA="$ISAAC_DIR/data"
KEY_PATH="$ISAAC_DATA/termux_bridge_id"
PUB_PATH="$KEY_PATH.pub"

echo "=== Isaac Termux-Brücke Setup ==="
echo "Isaac: $ISAAC_DIR"

if ! command -v pkg >/dev/null 2>&1; then
  echo "Fehler: pkg nicht gefunden — Skript in Termux ausführen." >&2
  exit 1
fi

pkg update -y
pkg install -y termux-api openssh tsu
mkdir -p "$BRIDGE_DIR" "$ISAAC_DATA"
chmod 700 "$BRIDGE_DIR"

if ! command -v termux-screenshot >/dev/null 2>&1; then
  echo "Hinweis: termux-screenshot fehlt — Termux:API-App installieren und Berechtigungen erlauben."
fi

if ! pgrep -x sshd >/dev/null 2>&1; then
  sshd || true
fi

if [ ! -f "$KEY_PATH" ]; then
  ssh-keygen -t ed25519 -N "" -f "$KEY_PATH" -C "isaac-termux-bridge"
fi

AUTH_LINE="$(cat "$PUB_PATH")"
MARKER="# isaac-termux-bridge"
AUTH_FILE="$TERMUX_HOME/.ssh/authorized_keys"
mkdir -p "$TERMUX_HOME/.ssh"
chmod 700 "$TERMUX_HOME/.ssh"
touch "$AUTH_FILE"
chmod 600 "$AUTH_FILE"
if ! grep -Fq "$MARKER" "$AUTH_FILE" 2>/dev/null; then
  echo "$AUTH_LINE $MARKER" >> "$AUTH_FILE"
fi

TERMUX_UID="$(stat -c '%u' /data/data/com.termux 2>/dev/null || echo "")"
SSH_USER="${ISAAC_TERMUX_SSH_USER:-u0_a${TERMUX_UID:-0}}"

ENV_FILE="$ISAAC_DIR/.env.local"
touch "$ENV_FILE"
grep -q '^ISAAC_TERMUX_BRIDGE=' "$ENV_FILE" 2>/dev/null || echo "ISAAC_TERMUX_BRIDGE=auto" >> "$ENV_FILE"
grep -q '^ISAAC_TERMUX_SSH_HOST=' "$ENV_FILE" 2>/dev/null || echo "ISAAC_TERMUX_SSH_HOST=127.0.0.1" >> "$ENV_FILE"
grep -q '^ISAAC_TERMUX_SSH_PORT=' "$ENV_FILE" 2>/dev/null || echo "ISAAC_TERMUX_SSH_PORT=8022" >> "$ENV_FILE"
grep -q '^ISAAC_TERMUX_SSH_IDENTITY=' "$ENV_FILE" 2>/dev/null || echo "ISAAC_TERMUX_SSH_IDENTITY=$KEY_PATH" >> "$ENV_FILE"
if ! grep -q '^ISAAC_TERMUX_SSH_USER=' "$ENV_FILE" 2>/dev/null; then
  echo "ISAAC_TERMUX_SSH_USER=$SSH_USER" >> "$ENV_FILE"
fi

echo ""
echo "Setup fertig."
echo "  Bridge-Workdir: $BRIDGE_DIR"
echo "  SSH-Key:        $KEY_PATH"
echo "  SSH-User:       $SSH_USER (ggf. in .env.local anpassen)"
echo ""
echo "Test in Isaac (Linux-Chroot):"
echo "  python3 -c \"import asyncio; from computer_use import get_computer_use, parse_agent_body; print(asyncio.run(get_computer_use().execute(parse_agent_body('diagnose'))))\""
echo ""
echo "Wichtig: Termux:API-App öffnen und Berechtigungen (Storage, Draw over, etc.) erlauben."