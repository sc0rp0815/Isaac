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

    def sync_constitutional_state(self) -> None:
        try:
            from constitution import get_constitution

            version = get_constitution().version()
            state = self.data.setdefault("constitutional_state", {})
            if state.get("constitution_version") != version:
                state["constitution_version"] = version
                self._save(self.data)
        except Exception as exc:
            log.debug("Constitution sync skipped: %s", exc)

    def record_owner_preference(
        self,
        key: str,
        value: Any,
        confidence: float = 0.7,
        source: str = "owner_feedback",
        evidence: str = "",
    ) -> dict[str, Any]:
        prefs = self.data.setdefault("preference_state", {})
        bucket = "avoid" if key == "avoid" else "owner_prefers"
        items = prefs.setdefault(bucket, [])
        if items and isinstance(items[0], str):
            items[:] = [{"key": "legacy", "value": v, "confidence": 0.5, "confirmations": 1} for v in items]

        normalized_key = (key or "preference").strip()[:80]
        normalized_value = str(value).strip()[:180]
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        existing = next(
            (item for item in items if item.get("key") == normalized_key and item.get("value") == normalized_value),
            None,
        )
        if existing:
            existing["confidence"] = min(1.0, float(existing.get("confidence", 0.5)) + 0.08)
            existing["confirmations"] = int(existing.get("confirmations", 1)) + 1
            existing["updated"] = ts
            existing["source"] = source
        else:
            existing = {
                "key": normalized_key,
                "value": normalized_value,
                "confidence": max(0.05, min(1.0, float(confidence))),
                "confirmations": 1,
                "source": source,
                "evidence": evidence[:200],
                "updated": ts,
            }
            items.append(existing)
        items.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)
        del items[20:]
        self._save(self.data)
        AuditLog.action("SelfModel", "record_preference", f"{bucket}:{normalized_key}")
        try:
            from memory import get_memory

            get_memory().log_development_event(
                event_type="preference_recorded",
                target_kind="self_model",
                target_key=normalized_key,
                delta=0.0,
                confidence_before=0.0,
                confidence_after=float(existing.get("confidence", confidence)),
                evidence_refs=[evidence[:120]] if evidence else [],
                reason=f"{source}: {normalized_value[:120]}",
                metadata={"bucket": bucket, "source": source},
            )
        except Exception as exc:
            log.debug("Preference development-log: %s", exc)
        return existing

    def reinforce_recent_preferences(self, boost: float = 0.05, reason: str = "") -> int:
        prefs = self.data.setdefault("preference_state", {})
        updated = 0
        for bucket in ("owner_prefers", "avoid"):
            for item in prefs.get(bucket, [])[-5:]:
                if not isinstance(item, dict):
                    continue
                before = float(item.get("confidence", 0.5))
                item["confidence"] = min(1.0, before + float(boost))
                item["confirmations"] = int(item.get("confirmations", 1)) + 1
                updated += 1
        if updated:
            self._save(self.data)
            AuditLog.development("preference_reinforced", "self_model", "recent", boost, reason)
        return updated

    def relevant_preferences(self, limit: int = 4, min_confidence: float = 0.55) -> list[dict[str, Any]]:
        prefs = self.data.get("preference_state", {})
        collected: list[dict[str, Any]] = []
        response_style = prefs.get("response_style")
        if response_style:
            collected.append({
                "key": "response_style",
                "value": response_style,
                "confidence": 0.8,
                "source": "self_model",
            })
        for bucket in ("owner_prefers", "avoid"):
            for item in prefs.get(bucket, []):
                if isinstance(item, str):
                    collected.append({"key": bucket, "value": item, "confidence": 0.5, "source": "legacy"})
                    continue
                conf = float(item.get("confidence", 0.0))
                if conf < min_confidence:
                    continue
                collected.append({
                    "key": item.get("key", bucket),
                    "value": item.get("value", ""),
                    "confidence": conf,
                    "source": item.get("source", "self_model"),
                    "confirmations": item.get("confirmations", 1),
                })
        collected.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)
        return collected[: max(1, int(limit))]

    def add_shared_theme(self, theme: str):
        self.track_shared_theme(theme)

    def track_shared_theme(self, theme: str) -> dict[str, Any] | None:
        theme = (theme or "").strip()[:80]
        if not theme:
            return None
        rel = self.data.setdefault("relationship_state", {})
        themes = rel.setdefault("shared_themes", [])
        if themes and isinstance(themes[0], str):
            themes[:] = [{"theme": t, "count": 1, "last_seen": time.strftime("%Y-%m-%d %H:%M:%S")} for t in themes]

        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        existing = next((item for item in themes if item.get("theme") == theme), None)
        if existing:
            existing["count"] = int(existing.get("count", 1)) + 1
            existing["last_seen"] = ts
        else:
            existing = {"theme": theme, "count": 1, "last_seen": ts}
            themes.append(existing)
        themes.sort(key=lambda item: int(item.get("count", 0)), reverse=True)
        del themes[12:]
        self._save(self.data)
        if int(existing.get("count", 0)) >= 2:
            return existing
        return None

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

    def bump_maturity(self, delta: float = 0.01) -> float:
        dev = self.data.setdefault("development_state", {})
        before = float(dev.get("maturity", 0.0) or 0.0)
        after = max(0.0, min(1.0, before + float(delta)))
        dev["maturity"] = after
        dev["last_reflection"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save(self.data)
        return after


_model: Optional[SelfModel] = None


def get_self_model() -> SelfModel:
    global _model
    if _model is None:
        _model = SelfModel()
    return _model
