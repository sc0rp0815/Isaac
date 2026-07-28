#!/usr/bin/env bash
# Start code-server for Isaac workspace (local S8 / chroot).
set -euo pipefail
export PATH="${HOME}/.local/bin:${PATH}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${HOME}/.config/code-server/config.yaml"
LOG="${ROOT}/logs/code-server.log"
mkdir -p "$(dirname "$CONFIG")" "${ROOT}/logs"
if [ ! -f "$CONFIG" ]; then
  PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')"
  cat > "$CONFIG" <<YAML
bind-addr: 0.0.0.0:8443
auth: password
password: ${PASS}
cert: false
YAML
  echo "$PASS" > "${ROOT}/data/cli_auth_backup/code_server_password.txt"
  chmod 600 "${ROOT}/data/cli_auth_backup/code_server_password.txt" 2>/dev/null || true
  echo "Generated password → data/cli_auth_backup/code_server_password.txt"
fi
# already listening?
if ss -ltn 2>/dev/null | grep -q ':8443'; then
  echo "code-server already on :8443"
  exit 0
fi
nohup code-server --config "$CONFIG" "$ROOT" >> "$LOG" 2>&1 &
echo "started pid $!  log=$LOG"
echo "URL: http://127.0.0.1:8443  (or http://<device-ip>:8443)"
if [ -f "${ROOT}/data/cli_auth_backup/code_server_password.txt" ]; then
  echo "Password file: data/cli_auth_backup/code_server_password.txt"
fi
