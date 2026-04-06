#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$HOME/Isaac/isaac}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${TARGET_DIR}_backup_${STAMP}"
PACKAGE_DIR="$SCRIPT_DIR/package"
TMP_ENV=""

log() { printf '\n[%s] %s\n' "$1" "$2"; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Fehlt: $1"; exit 1; }; }

log 1 "Vorprüfung"
need_cmd cp
need_cmd mkdir
need_cmd python3
need_cmd bash

if [ ! -d "$PACKAGE_DIR" ]; then
  echo "Paketordner fehlt: $PACKAGE_DIR"
  exit 1
fi

log 2 "Zielordner vorbereiten"
mkdir -p "$TARGET_DIR"
if [ -n "$(ls -A "$TARGET_DIR" 2>/dev/null || true)" ]; then
  echo "Backup wird erstellt: $BACKUP_DIR"
  mkdir -p "$BACKUP_DIR"
  cp -a "$TARGET_DIR"/. "$BACKUP_DIR"/
fi

if [ -f "$TARGET_DIR/.env" ]; then
  TMP_ENV="$(mktemp)"
  cp "$TARGET_DIR/.env" "$TMP_ENV"
fi

log 3 "Dateien kopieren"
cp -a "$PACKAGE_DIR"/. "$TARGET_DIR"/

if [ -n "$TMP_ENV" ] && [ -f "$TMP_ENV" ]; then
  cp "$TMP_ENV" "$TARGET_DIR/.env"
  rm -f "$TMP_ENV"
fi

if [ ! -f "$TARGET_DIR/.env" ] && [ -f "$TARGET_DIR/.env.example" ]; then
  cp "$TARGET_DIR/.env.example" "$TARGET_DIR/.env"
fi

chmod +x "$TARGET_DIR"/*.sh 2>/dev/null || true

log 4 "Python-Umgebung erkennen"
PYTHON_BIN="python3"
PIP_CMD="python3 -m pip"
if [ -d "$TARGET_DIR/.venv" ] && [ -x "$TARGET_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$TARGET_DIR/.venv/bin/python"
  PIP_CMD="$TARGET_DIR/.venv/bin/python -m pip"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PYTHON_BIN="$VIRTUAL_ENV/bin/python"
  PIP_CMD="$VIRTUAL_ENV/bin/python -m pip"
fi

echo "Python: $PYTHON_BIN"

log 5 "Abhängigkeiten installieren"
if [ -f "$TARGET_DIR/requirements.txt" ]; then
  set +e
  eval "$PIP_CMD install -r \"$TARGET_DIR/requirements.txt\""
  PIP_STATUS=$?
  set -e
  if [ "$PIP_STATUS" -ne 0 ]; then
    echo "Hinweis: pip-Installation fehlgeschlagen. In Alpine/externally-managed Umgebungen bitte venv nutzen."
  fi
fi

log 6 "Smoke-Test"
"$PYTHON_BIN" - <<PY
import compileall, sys
from pathlib import Path

target = Path(r"$TARGET_DIR").resolve()
ok = compileall.compile_dir(str(target), quiet=1, force=True)
print(f"compileall_ok={ok}")
if not ok:
    sys.exit(1)
mods = [
    "config","audit","memory","logic","privilege","sudo_gate","decomposer",
    "dispatcher","search","regelwerk","empathie","watchdog","relay",
    "executor","browser","ki_dialog","ki_skills","background_loop",
    "monitor_server","tool_registry","secrets_store","tool_runtime",
    "learning_engine","trust_engine","dashboard_api","isaac_core"
]
sys.path.insert(0, str(target))
failed = []
for m in mods:
    try:
        __import__(m)
    except Exception as e:
        failed.append((m, str(e)))
if failed:
    print("IMPORT_FAILURES:")
    for m,e in failed:
        print(f"- {m}: {e}")
    sys.exit(2)
print("import_smoke_ok=True")
PY

log 7 "Abschluss"
echo "Installiert in: $TARGET_DIR"
echo "Backup: $BACKUP_DIR"
echo
echo "Nächste Schritte:"
echo "1) .env prüfen: $TARGET_DIR/.env"
echo "2) Start: cd \"$TARGET_DIR\" && bash start_isaac.sh"
echo "3) Alternativ: cd \"$TARGET_DIR\" && $PYTHON_BIN isaac_core.py"
