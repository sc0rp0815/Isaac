#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
for name in isaac_core monitor_server; do
  pidfile="runtime/${name}.pid"
  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile")"
    if kill "$pid" >/dev/null 2>&1; then
      echo "Stopped $name ($pid)"
    else
      echo "Could not stop $name ($pid); maybe already dead"
    fi
    rm -f "$pidfile"
  fi
done
