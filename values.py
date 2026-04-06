from __future__ import annotations

"""Isaac – Values Module
Dynamische Werte, die aus Erfahrungen abgeleitet werden.
"""

import json
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config import DATA_DIR
from audit import AuditLog

log = logging.getLogger("Isaac.Values")
VALUES_PATH = DATA_DIR / "values.json"


@dataclass
class Value:
    name: str
    strength: float = 0.5
    evidence: List[str] = field(default_factory=list)
    updated: float = field(default_factory=time.time)


class ValueSystem:
    def __init__(self):
        self._values: Dict[str, Value] = {}
        self._load()

    def _load(self):
        if VALUES_PATH.exists():
            try:
                data = json.loads(VALUES_PATH.read_text(encoding="utf-8"))
                for k, v in data.items():
                    self._values[k] = Value(**v)
            except Exception as e:
                log.debug(f"ValueSystem load fehlgeschlagen: {e}")

    def _save(self):
        VALUES_PATH.write_text(json.dumps({k: {
            "name": v.name,
            "strength": v.strength,
            "evidence": v.evidence[-5:],
            "updated": v.updated
        } for k, v in self._values.items()}, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_concept(concept: str) -> str:
        return concept.strip().lower().replace(" ", "_")

    def update(self, concept: str, delta: float, reason: str):
        concept = self._normalize_concept(concept)
        if concept not in self._values:
            self._values[concept] = Value(name=concept)
        v = self._values[concept]
        v.strength = max(0.0, min(1.0, v.strength + float(delta)))
        v.evidence.append(reason[:200])
        v.updated = time.time()
        self._save()
        AuditLog.action("ValueSystem", "update", f"{concept} -> {v.strength:.2f}")

    def get(self, concept: str, default: float = 0.5) -> float:
        concept = self._normalize_concept(concept)
        return self._values.get(concept, Value(concept, strength=default)).strength

    def list_values(self) -> List[dict]:
        return [{"name": v.name, "strength": v.strength, "evidence": v.evidence[-3:]} for v in self._values.values()]

    def top_values(self, n: int = 5) -> List[dict]:
        sorted_vals = sorted(self._values.values(), key=lambda v: v.strength, reverse=True)
        return [{"name": v.name, "strength": v.strength} for v in sorted_vals[:n]]


_values: Optional[ValueSystem] = None


def get_values() -> ValueSystem:
    global _values
    if _values is None:
        _values = ValueSystem()
    return _values
