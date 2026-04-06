from __future__ import annotations

"""Isaac – Meaning / Impact Store
Speichert wahrgenommene Bedeutung, Wirkung und Bindung.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from config import DATA_DIR
from audit import AuditLog

log = logging.getLogger("Isaac.Meaning")
MEANING_PATH = DATA_DIR / "meaning.json"


class ImpactType(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass
class MeaningEntry:
    key: str
    importance: float = 0.5
    evidence: List[str] = field(default_factory=list)
    updated: float = field(default_factory=time.time)


class MeaningStore:
    def __init__(self):
        self._entries: Dict[str, MeaningEntry] = {}
        self._load()

    def _load(self):
        try:
            if MEANING_PATH.exists():
                data = json.loads(MEANING_PATH.read_text(encoding="utf-8"))
                for k, v in data.items():
                    self._entries[k] = MeaningEntry(**v)
        except Exception as e:
            log.debug(f"Meaning load fehlgeschlagen: {e}")

    def _save(self):
        try:
            MEANING_PATH.write_text(json.dumps({k: {
                "key": v.key,
                "importance": v.importance,
                "evidence": v.evidence[-5:],
                "updated": v.updated
            } for k, v in self._entries.items()}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log.debug(f"Meaning save fehlgeschlagen: {e}")

    @staticmethod
    def _normalize_key(key: str) -> str:
        return key.strip().lower().replace(" ", "_")

    def update(self, key: str, delta: float, reason: str = ""):
        key = self._normalize_key(key)
        entry = self._entries.get(key)
        if entry is None:
            entry = MeaningEntry(key=key)
            self._entries[key] = entry
        entry.importance = max(0.0, min(1.0, entry.importance + float(delta) * 0.1))
        if reason:
            entry.evidence.append(reason[:200])
        entry.updated = time.time()
        self._save()
        AuditLog.action("Meaning", "update", f"{key} -> {entry.importance:.2f}")

    def get_importance(self, key: str, default: float = 0.5) -> float:
        key = self._normalize_key(key)
        return self._entries.get(key, MeaningEntry(key=key, importance=default)).importance

    def get(self, key: str, default: float = 0.5):
        """
        Dict-kompatibler Zugriff für Altcode.
        Gibt standardmäßig die Importance des Keys zurück.
        """
        return self.get_importance(key, default)

    def record_impact(self, target: str, action: str, impact: str | ImpactType, weight: float = 1.0, reason: str = ""):
        target_norm = self._normalize_key(target)
        action_norm = self._normalize_key(action)
        if isinstance(impact, ImpactType):
            impact = impact.value
        impact = str(impact).strip().lower()
        entry_key = f"impact_{target_norm}_{action_norm}"
        delta = weight if impact == "positive" else (-weight if impact == "negative" else 0.0)
        if delta != 0:
            self.update(entry_key, delta, f"Impact on {target_norm}: {reason}")
        if target_norm == "steffen":
            self.update("bonding_steffen", delta, f"Bonding: {reason}")

    def get_bonding(self, target: str) -> float:
        return self.get_importance(f"bonding_{self._normalize_key(target)}")

    def get_action_impact(self, action: str, target: str = "Steffen") -> float:
        return self.get_importance(f"impact_{self._normalize_key(target)}_{self._normalize_key(action)}")

    def summary(self) -> list[dict]:
        vals = sorted(self._entries.values(), key=lambda x: x.importance, reverse=True)
        return [{"key": v.key, "importance": v.importance, "evidence": v.evidence[-2:]} for v in vals[:10]]


_meaning: Optional[MeaningStore] = None


def get_meaning() -> MeaningStore:
    global _meaning
    if _meaning is None:
        _meaning = MeaningStore()
    return _meaning
