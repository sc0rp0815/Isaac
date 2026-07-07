#!/usr/bin/env bash
set -euo pipefail

PKG_ZIP="${PKG_ZIP:-$HOME/storage/shared/Gpt-isaac/deploy/isaac_complete_openrouter_values_patch.zip}"
TARGET_DIR="${1:-/storage/emulated/0/Gpt-isaac/deploy/isaac_runtime}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${TARGET_DIR}_backup_${STAMP}"
TMP_DIR="$(mktemp -d)"

cleanup(){ rm -rf "$TMP_DIR"; }
trap cleanup EXIT

echo "[1/8] Paket prüfen ..."
[ -f "$PKG_ZIP" ] || { echo "Paket nicht gefunden: $PKG_ZIP"; exit 1; }
mkdir -p "$TARGET_DIR"
if [ -n "$(ls -A "$TARGET_DIR" 2>/dev/null || true)" ]; then
  echo "[2/8] Backup: $BACKUP_DIR"
  mkdir -p "$BACKUP_DIR"
  cp -a "$TARGET_DIR"/. "$BACKUP_DIR"/
else
  echo "[2/8] Leeres Zielverzeichnis wird vorbereitet ..."
fi

echo "[3/8] Paket entpacken ..."
unzip -oq "$PKG_ZIP" -d "$TMP_DIR"
PKG_ROOT="$TMP_DIR"
for cand in "$TMP_DIR"/*; do
  if [ -d "$cand" ] && [ -f "$cand/isaac_core.py" ]; then PKG_ROOT="$cand"; break; fi
done
if [ -f "$TARGET_DIR/.env" ]; then cp "$TARGET_DIR/.env" "$TMP_DIR/user.env.keep"; fi

echo "[4/8] Dateien kopieren ..."
cp -a "$PKG_ROOT"/. "$TARGET_DIR"/
if [ -f "$TMP_DIR/user.env.keep" ]; then cp "$TMP_DIR/user.env.keep" "$TARGET_DIR/.env"; fi
if [ ! -f "$TARGET_DIR/.env" ] && [ -f "$TARGET_DIR/.env.example" ]; then cp "$TARGET_DIR/.env.example" "$TARGET_DIR/.env"; fi
chmod +x "$TARGET_DIR"/*.sh 2>/dev/null || true

echo "[5/8] Python-Abhängigkeiten installieren ..."
python3 -m pip install --upgrade pip wheel setuptools
python3 -m pip install -r "$TARGET_DIR/requirements.txt"

echo "[6/8] Browser-Komponenten sicherstellen ..."
python3 -m playwright install chromium || true

echo "[7/8] Compile-/Import-Test ..."
export TARGET_DIR
python3 - <<'INNERPY'
import compileall, os, sys
root = os.path.abspath(os.environ.get("TARGET_DIR", "."))
sys.path.insert(0, root)
mods = ["config","audit","logic","memory","privilege","sudo_gate","decomposer","dispatcher","search","regelwerk","empathie","watchdog","relay","executor","browser","ki_dialog","ki_skills","background_loop","monitor_server","tool_registry","secrets_store","tool_runtime","learning_engine","trust_engine","dashboard_api","instincts","values","meaning","value_decisions","reflection"]
ok = compileall.compile_dir(root, quiet=1, force=True)
print(f"compileall_ok={ok}")
failed=[]
for m in mods:
    try:
        __import__(m)
    except Exception as e:
        failed.append((m, str(e)))
if failed:
    print("IMPORT_FAILURES:")
    for m,e in failed:
        print(f"- {m}: {e}")
print("done")
INNERPY

echo "[8/8] Fertig."
echo "Installiert in: $TARGET_DIR"
echo "Backup: $BACKUP_DIR"
echo "Start: cd \"$TARGET_DIR\" && python3 isaac_core.py"
