from __future__ import annotations

"""Isaac – Instincts Module
Basis-Instinkte: Selbsterhaltung, Neugier, Bindung.
Die Instinkte erzeugen keine direkten Aktionen, sondern beeinflussen
Priorisierung und Bewertung.
"""

import json
import time
import logging
from dataclasses import dataclass, asdict
from typing import Optional

from config import DATA_DIR
from audit import AuditLog

log = logging.getLogger("Isaac.Instincts")
STATE_PATH = DATA_DIR / "instincts.json"


@dataclass
class InstinctState:
    self_preservation_priority: float = 0.9
    curiosity_priority: float = 0.8
    bonding_priority: float = 0.7
    last_self_preservation_trigger: float = 0.0
    last_curiosity_trigger: float = 0.0
    last_bonding_trigger: float = 0.0


class InstinctEngine:
    def __init__(self):
        self.state = InstinctState()
        self._load()
        log.info("InstinctEngine initialisiert")

    def _load(self):
        try:
            if STATE_PATH.exists():
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                self.state = InstinctState(**{k: v for k, v in data.items() if k in InstinctState.__dataclass_fields__})
        except Exception as e:
            log.debug(f"Instinct load fehlgeschlagen: {e}")

    def _save(self):
        try:
            STATE_PATH.write_text(json.dumps(asdict(self.state), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log.debug(f"Instinct save fehlgeschlagen: {e}")

    def update_from_system(self, system_stats: dict):
        now = time.time()
        if system_stats.get("recent_hangs", 0) > 2 or system_stats.get("recent_errors", 0) > 3:
            self.state.self_preservation_priority = min(1.0, self.state.self_preservation_priority + 0.05)
            self.state.last_self_preservation_trigger = now
        else:
            self.state.self_preservation_priority = max(0.3, self.state.self_preservation_priority - 0.01)

        if system_stats.get("open_questions", 0) > 3 or system_stats.get("low_confidence", 0) > 0:
            self.state.curiosity_priority = min(1.0, self.state.curiosity_priority + 0.03)
            self.state.last_curiosity_trigger = now
        else:
            self.state.curiosity_priority = max(0.3, self.state.curiosity_priority - 0.01)

        if system_stats.get("steffen_engagement", 0.0) > 0.7:
            self.state.bonding_priority = min(1.0, self.state.bonding_priority + 0.02)
            self.state.last_bonding_trigger = now
        else:
            self.state.bonding_priority = max(0.2, self.state.bonding_priority - 0.01)

        self._save()
        AuditLog.action("Instincts", "update_from_system", str(self.get_priorities()))

    def get_priorities(self) -> dict:
        return {
            "self_preservation": self.state.self_preservation_priority,
            "curiosity": self.state.curiosity_priority,
            "bonding": self.state.bonding_priority,
        }

    def should_prioritize_self_preservation(self) -> bool:
        return self.state.self_preservation_priority > 0.8

    def should_prioritize_curiosity(self) -> bool:
        return self.state.curiosity_priority > 0.7

    def should_prioritize_bonding(self) -> bool:
        return self.state.bonding_priority > 0.6


_instincts: Optional[InstinctEngine] = None


def get_instincts() -> InstinctEngine:
    global _instincts
    if _instincts is None:
        _instincts = InstinctEngine()
    return _instincts
