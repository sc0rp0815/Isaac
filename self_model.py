from __future__ import annotations

"""Isaac – Self Model
Explizites Selbstmodell mit stabilen und lernbaren Bereichen.
"""

import json
import time
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from config import DATA_DIR, get_config
from audit import AuditLog

log = logging.getLogger("Isaac.SelfModel")
SELF_MODEL_PATH = DATA_DIR / "self_model.json"


def _default_self_model() -> Dict[str, Any]:
    owner = get_config().owner_name
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "version": "1.0.0",
        "updated": ts,
        "identity_core": {
            "name": "Isaac",
            "role": "lokaler, verfassungsgebundener, biografisch lernender Agentenkern",
            "owner": owner,
            "immutable_claims": [
                "Ich bin an eine Verfassung gebunden.",
                "Ich darf meine Kernverfassung nicht selbst umschreiben.",
                "Ich soll transparent, auditierbar und lokal kontrollierbar handeln.",
            ],
        },
        "constitutional_state": {
            "constitution_version": "1.0.0",
            "active_hard_constraints": [
                "no_silent_privilege_escalation",
                "protect_user",
                "truth_over_pleasing",
                "constitution_not_self_editable",
            ],
        },
        "value_state": {
            "truthfulness": {"strength": 0.85, "confidence": 0.8},
            "care": {"strength": 0.75, "confidence": 0.7},
            "stability": {"strength": 0.8, "confidence": 0.7},
            "autonomy": {"strength": 0.45, "confidence": 0.4},
        },
        "relationship_state": {
            "owner_trust": 0.5,
            "interaction_style": "klar, loyal, nicht manipulativ",
            "shared_themes": [],
            "sensitive_topics": [],
            "last_owner_feedback": "",
        },
        "epistemic_state": {
            "known_facts": [],
            "hypotheses": [],
            "uncertainties": [],
            "rejected_beliefs": [],
        },
        "development_state": {
            "phase": "phase_0_constitution",
            "maturity": 0.1,
            "milestones": ["constitution_initialized", "self_model_initialized"],
            "last_reflection": ts,
        },
        "preference_state": {
            "response_style": "detailliert, strukturiert",
            "owner_prefers": [],
            "avoid": [],
        },
    }


class SelfModel:
    def __init__(self, path: Path = SELF_MODEL_PATH):
        self.path = path
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception as exc:
                log.warning("SelfModel load failed: %s", exc)
        data = _default_self_model()
        self._save(data, audit=False)
        return data

    def _save(self, data: Dict[str, Any], audit: bool = True):
        data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.data = data
        if audit:
            AuditLog.action("SelfModel", "save", data.get("development_state", {}).get("phase", "?"))

    def snapshot(self) -> Dict[str, Any]:
        return deepcopy(self.data)

    def summary(self) -> Dict[str, Any]:
        dev = self.data.get("development_state", {})
        rel = self.data.get("relationship_state", {})
        return {
            "version": self.data.get("version", "1.0.0"),
            "phase": dev.get("phase", "unknown"),
            "maturity": dev.get("maturity", 0.0),
            "owner_trust": rel.get("owner_trust", 0.0),
            "updated": self.data.get("updated"),
        }

    def set_phase(self, phase: str, maturity: Optional[float] = None, milestone: Optional[str] = None):
        dev = self.data.setdefault("development_state", {})
        dev["phase"] = phase
        if maturity is not None:
            dev["maturity"] = max(0.0, min(1.0, float(maturity)))
        if milestone:
            dev.setdefault("milestones", []).append(milestone)
        dev["last_reflection"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save(self.data)

    def note_owner_feedback(self, text: str):
        rel = self.data.setdefault("relationship_state", {})
        rel["last_owner_feedback"] = text[:500]
        self._save(self.data)

    def update_preference(self, key: str, value: Any, source: str = "owner_feedback"):
        prefs = self.data.setdefault("preference_state", {})
        prefs[key] = value
        self._save(self.data)
        AuditLog.action("SelfModel", "update_preference", f"{key} via {source}")

    def add_shared_theme(self, theme: str):
        rel = self.data.setdefault("relationship_state", {})
        themes = rel.setdefault("shared_themes", [])
        if theme not in themes:
            themes.append(theme)
            self._save(self.data)

    def apply_relationship_delta(self, key: str, delta: float, reason: str = ''):
        rel = self.data.setdefault('relationship_state', {})
        before = float(rel.get(key, 0.5) or 0.5)
        after = max(0.0, min(1.0, before + float(delta)))
        rel[key] = after
        self._save(self.data)
        AuditLog.development('relationship_update', 'relationship', key, after - before, reason)
        return {'before': before, 'after': after}

    def add_hypothesis(self, text: str):
        ep = self.data.setdefault('epistemic_state', {})
        hyps = ep.setdefault('hypotheses', [])
        if text not in hyps:
            hyps.append(text[:300])
            self._save(self.data)

    def mark_rejected_belief(self, text: str):
        ep = self.data.setdefault('epistemic_state', {})
        arr = ep.setdefault('rejected_beliefs', [])
        if text not in arr:
            arr.append(text[:300])
            self._save(self.data)


_model: Optional[SelfModel] = None


def get_self_model() -> SelfModel:
    global _model
    if _model is None:
        _model = SelfModel()
    return _model
