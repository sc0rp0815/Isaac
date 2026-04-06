from __future__ import annotations
import json, time
from dataclasses import dataclass, asdict
from pathlib import Path
from config import DATA_DIR
PATH = DATA_DIR / 'learning_events.jsonl'
@dataclass
class LearningEvent:
    ts: float
    prompt: str
    route: str
    outcome: str
    score: float = 0.0
    notes: str = ''
class LearningEngine:
    def learn(self, prompt: str, route: str, outcome: str, score: float = 0.0, notes: str = ''):
        ev = LearningEvent(time.time(), prompt[:1000], route, outcome, score, notes[:1000])
        with PATH.open('a', encoding='utf-8') as f: f.write(json.dumps(asdict(ev), ensure_ascii=False)+'\n')
    def recent(self, n: int = 50):
        if not PATH.exists(): return []
        lines = PATH.read_text(encoding='utf-8').splitlines()[-n:]
        return [json.loads(x) for x in lines if x.strip()]
_engine = None
def get_learning_engine() -> LearningEngine:
    global _engine
    if _engine is None: _engine = LearningEngine()
    return _engine
