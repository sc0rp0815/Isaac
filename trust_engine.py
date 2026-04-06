from __future__ import annotations
import json
from pathlib import Path
from config import DATA_DIR
PATH = DATA_DIR / 'trust.json'
class TrustEngine:
    def __init__(self):
        self._db = {}
        if PATH.exists():
            try: self._db = json.loads(PATH.read_text(encoding='utf-8'))
            except Exception: self._db = {}
    def _save(self): PATH.write_text(json.dumps(self._db, ensure_ascii=False, indent=2), encoding='utf-8')
    def get(self, entity: str, default: float = 50.0) -> float: return float(self._db.get(entity, default))
    def update(self, entity: str, delta: float):
        self._db[entity] = max(0.0, min(100.0, self.get(entity)+delta)); self._save(); return self._db[entity]
_engine = None
def get_trust_engine() -> TrustEngine:
    global _engine
    if _engine is None: _engine = TrustEngine()
    return _engine
