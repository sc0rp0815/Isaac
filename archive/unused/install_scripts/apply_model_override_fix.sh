#!/data/data/com.termux/files/usr/bin/bash
set -e
TARGET_DIR="${1:-$(pwd)}"
cd "$TARGET_DIR"
python3 - <<'PY'
from pathlib import Path
p = Path('relay.py')
if not p.exists():
    raise SystemExit('relay.py nicht gefunden')
s = p.read_text()
old = '''    async def ask(self, prompt: str,\n                  system: str = "Du bist Isaac, ein autonomes KI-System.",\n                  provider: Optional[str] = None,\n                  context: str = "",\n                  use_cache: bool = True,\n                  tokens: int = 0,\n                  task_id: str = "") -> str:\n'''
new = '''    async def ask(self, prompt: str,\n                  system: str = "Du bist Isaac, ein autonomes KI-System.",\n                  provider: Optional[str] = None,\n                  context: str = "",\n                  use_cache: bool = True,\n                  tokens: int = 0,\n                  task_id: str = "",\n                  model_override: Optional[str] = None) -> str:\n'''
if new in s:
    print('relay.py bereits gepatcht')
elif old in s:
    p.write_text(s.replace(old, new, 1))
    print('relay.py gepatcht')
else:
    raise SystemExit('erwartete ask()-Signatur in relay.py nicht gefunden')
PY
python3 -m py_compile relay.py
printf '[Isaac] Fix erfolgreich angewendet in %s\n' "$TARGET_DIR"
