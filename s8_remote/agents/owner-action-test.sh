#!/data/data/com.termux/files/usr/bin/bash
# S8+ Hub-Agent: Owner-Action Live-Test
set -euo pipefail

ISAAC_DIR="${ISAAC_DIR:-$HOME/Isaac}"
cd "$ISAAC_DIR"

export ISAAC_DISABLE_VECTOR_MEMORY=1
export ISAAC_PRIVILEGE_MODE=admin
export ISAAC_RUNTIME_ENV=termux

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "=== Owner-Action Live-Test (S8) ==="
echo "Zeit: $(date -Iseconds 2>/dev/null || date)"
echo "Pfad: $ISAAC_DIR"
echo ""

python3 scripts/owner_action_live_test.py --detect-only
DETECT_RC=$?

echo ""
python3 scripts/owner_action_live_test.py --live
LIVE_RC=$?

echo ""
if [ "$DETECT_RC" -eq 0 ] && [ "$LIVE_RC" -eq 0 ]; then
  echo "S8 Live-Test: OK"
  exit 0
fi
echo "S8 Live-Test: FEHLER (detect=$DETECT_RC live=$LIVE_RC)"
exit 1