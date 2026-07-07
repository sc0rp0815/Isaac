#!/usr/bin/env bash
set -euo pipefail

PKG_ZIP="${PKG_ZIP:-/mnt/data/isaac_complete_integrated_package_v7.zip}"
TARGET_DIR="${1:-$HOME/Isaac/isaac}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${TARGET_DIR}_backup_${STAMP}"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "[1/7] Prüfe Paket ..."
if [ ! -f "$PKG_ZIP" ]; then
  echo "Paket nicht gefunden: $PKG_ZIP"
  exit 1
fi

echo "[2/7] Zielordner vorbereiten ..."
mkdir -p "$TARGET_DIR"

if [ -n "$(ls -A "$TARGET_DIR" 2>/dev/null || true)" ]; then
  echo "Backup wird erstellt: $BACKUP_DIR"
  mkdir -p "$BACKUP_DIR"
  cp -a "$TARGET_DIR"/. "$BACKUP_DIR"/
fi

echo "[3/7] Paket entpacken ..."
unzip -oq "$PKG_ZIP" -d "$TMP_DIR"

PKG_ROOT="$TMP_DIR"
if [ -d "$TMP_DIR/isaac_complete_integrated_package_v7" ]; then
  PKG_ROOT="$TMP_DIR/isaac_complete_integrated_package_v7"
fi

echo "[4/7] Dateien kopieren ..."
# .env des Nutzers schützen
if [ -f "$TARGET_DIR/.env" ]; then
  cp "$TARGET_DIR/.env" "$TMP_DIR/user.env.keep"
fi

cp -a "$PKG_ROOT"/. "$TARGET_DIR"/

if [ -f "$TMP_DIR/user.env.keep" ]; then
  cp "$TMP_DIR/user.env.keep" "$TARGET_DIR/.env"
fi

if [ ! -f "$TARGET_DIR/.env" ] && [ -f "$TARGET_DIR/.env.example" ]; then
  cp "$TARGET_DIR/.env.example" "$TARGET_DIR/.env"
fi

chmod +x "$TARGET_DIR"/*.sh 2>/dev/null || true

echo "[5/7] Python-Abhängigkeiten installieren ..."
if [ -f "$TARGET_DIR/requirements.txt" ]; then
  python3 -m pip install -r "$TARGET_DIR/requirements.txt"
fi

echo "[6/7] Smoke-Test ..."
python3 - <<PY
import compileall, os, sys
target = os.path.abspath("$TARGET_DIR")
ok = compileall.compile_dir(target, quiet=1, force=True)
print(f"compileall_ok={ok}")
if not ok:
    sys.exit(1)

mods = [
    "config","audit","memory","logic","privilege","sudo_gate","decomposer",
    "dispatcher","search","regelwerk","empathie","watchdog","relay",
    "executor","browser","ki_dialog","ki_skills","background_loop",
    "monitor_server","tool_registry","secrets_store","tool_runtime",
    "learning_engine","trust_engine","dashboard_api"
]
sys.path.insert(0, target)
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

echo "[7/7] Fertig."
echo
echo "Installiert in: $TARGET_DIR"
echo "Backup:          $BACKUP_DIR"
echo
echo "Nächste Schritte:"
echo "1) Prüfe/fülle .env in: $TARGET_DIR/.env"
echo "2) Optional Browser-Chat-Selektoren in Tool-Registry pflegen"
echo "3) Starten mit:"
echo "   cd \"$TARGET_DIR\" && python3 isaac_core.py"
echo "   oder:"
echo "   cd \"$TARGET_DIR\" && bash start_isaac.sh"
