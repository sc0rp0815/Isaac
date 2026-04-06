from __future__ import annotations
import json, time
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SECRETS_FILE = DATA_DIR / "secrets_store.json"

class SecretsStore:
    def __init__(self, path: Path = SECRETS_FILE):
        self.path = path
        self._cache = {}
        self._load()

    def _load(self):
        if not self.path.exists():
            self._save()
            return
        try:
            self._cache = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._cache = {}
            self._save()

    def _save(self):
        self.path.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_secret(self, ref: str, value: str, kind: str = "api_key"):
        self._cache[ref] = {"value": value, "kind": kind, "updated_at": time.time()}
        self._save()

    def get_secret(self, ref: str):
        row = self._cache.get(ref)
        return row.get("value") if row else None

_store = None
def get_secrets_store() -> SecretsStore:
    global _store
    if _store is None:
        _store = SecretsStore()
    return _store
