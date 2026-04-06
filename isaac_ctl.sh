#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_TARGET="${ISAAC_TARGET_DIR:-$HOME/Isaac/isaac}"

pick_python() {
  local base="$1"
  if [ -x "$base/.venv/bin/python" ]; then
    echo "$base/.venv/bin/python"
  else
    command -v python3
  fi
}

show_menu() {
  cat <<EOF
Isaac Control
=============
1) Install to target ($DEFAULT_TARGET)
2) Start installed Isaac ($DEFAULT_TARGET)
3) Start bundled Isaac here
4) Run healthcheck on installed target
5) Run healthcheck on bundled package
6) Tail installed log
7) Open shell in installed target
EOF
}

cmd="${1:-menu}"
case "$cmd" in
  install)
    exec bash "$ROOT_DIR/install_master.sh" "${2:-$DEFAULT_TARGET}"
    ;;
  start)
    TARGET="${2:-$DEFAULT_TARGET}"
    cd "$TARGET"
    PY="$(pick_python "$TARGET")"
    exec "$PY" isaac_core.py
    ;;
  start-bundle)
    exec bash "$ROOT_DIR/start_master_here.sh"
    ;;
  healthcheck)
    TARGET="${2:-$DEFAULT_TARGET}"
    PY="$(pick_python "$TARGET")"
    cd "$TARGET"
    exec "$PY" healthcheck_isaac.py
    ;;
  healthcheck-bundle)
    PY="$(pick_python "$ROOT_DIR/package")"
    cd "$ROOT_DIR/package"
    exec "$PY" healthcheck_isaac.py
    ;;
  logs)
    TARGET="${2:-$DEFAULT_TARGET}"
    exec tail -n 100 -f "$TARGET/logs/isaac.log"
    ;;
  shell)
    TARGET="${2:-$DEFAULT_TARGET}"
    cd "$TARGET"
    exec "${SHELL:-/bin/sh}"
    ;;
  menu)
    show_menu
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    echo "Usage: $0 {menu|install|start|start-bundle|healthcheck|healthcheck-bundle|logs|shell} [target_dir]" >&2
    exit 2
    ;;
esac
