from __future__ import annotations

"""Isaac – Self Model
Explizites Selbstmodell mit stabilen und lernbaren Bereichen.
"""

import json
import re
import time
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from config import DATA_DIR, get_config
from audit import AuditLog

log = logging.getLogger("Isaac.SelfModel")
SELF_MODEL_PATH = DATA_DIR / "self_model.json"
CONFIRMED_CONFIDENCE_THRESHOLD = 0.75
MEMORY_SYNC_MIN_CONFIRMATIONS = 2


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
        self._pending_confirmation: list[tuple[str, str]] = []

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

    @staticmethod
    def _preference_fact_key(entry: dict[str, Any]) -> str:
        base = (entry.get("key") or "preference").strip().lower()[:40]
        value_slug = re.sub(
            r"[^\w]+",
            "_",
            (entry.get("value") or "")[:40].lower(),
        ).strip("_")
        return f"pref.{base}.{value_slug}" if value_slug else f"pref.{base}"

    def _should_sync_preference_to_memory(self, entry: dict[str, Any]) -> bool:
        source = (entry.get("source") or "").strip()
        confidence = float(entry.get("confidence", 0.0) or 0.0)
        confirmations = int(entry.get("confirmations", 1) or 1)
        return (
            source == "owner_correction"
            or confidence >= CONFIRMED_CONFIDENCE_THRESHOLD
            or confirmations >= MEMORY_SYNC_MIN_CONFIRMATIONS
        )

    def sync_confirmed_preference_to_memory(self, entry: dict[str, Any]) -> bool:
        if not self._should_sync_preference_to_memory(entry):
            return False
        value = str(entry.get("value") or "").strip()
        if not value:
            return False
        try:
            from memory import get_memory

            fact_key = self._preference_fact_key(entry)
            get_memory().set_fact(
                fact_key,
                value[:500],
                source="Steffen",
                confidence=1.0,
            )
            return True
        except Exception as exc:
            log.debug("Preference memory-sync: %s", exc)
            return False

    def mark_pending_confirmation(self, key: str, value: str) -> None:
        normalized_key = (key or "").strip()[:80]
        normalized_value = str(value or "").strip()[:180]
        if not normalized_key or not normalized_value:
            return
        pair = (normalized_key, normalized_value)
        pending = [item for item in self._pending_confirmation if item != pair]
        pending.append(pair)
        self._pending_confirmation = pending[-3:]

    def confirm_pending_preferences(self, boost: float = 0.06, reason: str = "") -> int:
        if not self._pending_confirmation:
            return 0
        prefs = self.data.setdefault("preference_state", {})
        targets = set(self._pending_confirmation)
        updated = 0
        confirmed_entries: list[dict[str, Any]] = []
        for bucket in ("owner_prefers", "avoid"):
            for item in prefs.get(bucket, []):
                if not isinstance(item, dict):
                    continue
                pair = (str(item.get("key", "")), str(item.get("value", "")))
                if pair not in targets:
                    continue
                before = float(item.get("confidence", 0.5))
                item["confidence"] = min(1.0, before + float(boost))
                item["confirmations"] = int(item.get("confirmations", 1)) + 1
                item["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
                item["source"] = "owner_confirmation"
                updated += 1
                confirmed_entries.append(item)
        response_style = prefs.get("response_style")
        for _key, value in targets:
            if _key != "response_style" or not response_style:
                continue
            for item in prefs.get("owner_prefers", []):
                if not isinstance(item, dict):
                    continue
                if item.get("key") == "response_style" and item.get("value") == value:
                    before = float(item.get("confidence", 0.5))
                    item["confidence"] = min(1.0, before + float(boost))
                    item["confirmations"] = int(item.get("confirmations", 1)) + 1
                    item["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    item["source"] = "owner_confirmation"
                    updated += 1
                    confirmed_entries.append(item)
            prefs["response_style"] = value
        if updated:
            self._save(self.data)
            AuditLog.development("preference_confirmed", "self_model", "pending", boost, reason)
            for entry in confirmed_entries:
                self.sync_confirmed_preference_to_memory(entry)
        self._pending_confirmation = []
        return updated

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
        if len(items) > 20:
            if existing in items[20:]:
                items.remove(existing)
                items.insert(19, existing)
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
        if source in {"owner_statement", "owner_correction", "owner_style_hint"}:
            self.mark_pending_confirmation(normalized_key, normalized_value)
        self.sync_confirmed_preference_to_memory(existing)
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

    def bump_value_strength(
        self,
        key: str,
        *,
        strength_delta: float = 0.01,
        confidence_delta: float = 0.005,
        reason: str = "",
    ) -> dict[str, float]:
        values = self.data.setdefault("value_state", {})
        entry = dict(values.get(key) or {"strength": 0.5, "confidence": 0.4})
        before_strength = float(entry.get("strength", 0.5) or 0.5)
        before_confidence = float(entry.get("confidence", 0.4) or 0.4)
        entry["strength"] = max(0.0, min(1.0, before_strength + float(strength_delta)))
        entry["confidence"] = max(0.0, min(1.0, before_confidence + float(confidence_delta)))
        values[key] = entry
        self._save(self.data)
        if reason:
            AuditLog.development("value_update", "value", key, entry["strength"] - before_strength, reason)
        return {
            "strength_before": before_strength,
            "strength_after": entry["strength"],
            "confidence_before": before_confidence,
            "confidence_after": entry["confidence"],
        }

    @staticmethod
    def _normalize_compare_value(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    @staticmethod
    def _values_semantically_conflict(left: str, right: str) -> bool:
        a = SelfModel._normalize_compare_value(left)
        b = SelfModel._normalize_compare_value(right)
        if not a or not b:
            return False
        if a == b:
            return False
        opposing = (
            ("kurz", "ausführlich"),
            ("kurz", "detailliert"),
            ("knapp", "ausführlich"),
            ("knapp", "lang"),
            ("nüchtern", "emotional"),
        )
        for token_a, token_b in opposing:
            if (token_a in a and token_b in b) or (token_b in a and token_a in b):
                return True
        return False

    def _iter_preference_entries(self) -> list[dict[str, Any]]:
        prefs = self.data.get("preference_state", {})
        entries: list[dict[str, Any]] = []
        response_style = prefs.get("response_style")
        if response_style:
            entries.append({
                "bucket": "response_style",
                "key": "response_style",
                "value": response_style,
                "confidence": 0.8,
            })
        for bucket in ("owner_prefers", "avoid"):
            for item in prefs.get(bucket, []):
                if isinstance(item, str):
                    entries.append({
                        "bucket": bucket,
                        "key": bucket,
                        "value": item,
                        "confidence": 0.5,
                    })
                    continue
                if not isinstance(item, dict):
                    continue
                entries.append({
                    "bucket": bucket,
                    "key": item.get("key", bucket),
                    "value": item.get("value", ""),
                    "confidence": float(item.get("confidence", 0.0) or 0.0),
                })
        return entries

    def detect_fact_contradictions(self, memory: Any = None) -> list[dict[str, Any]]:
        """Erkennt Widersprüche zwischen Self-Model-Präferenzen und Memory-Fakten."""
        contradictions: list[dict[str, Any]] = []
        entries = self._iter_preference_entries()
        prefers = [e for e in entries if e.get("bucket") != "avoid"]
        avoids = [e for e in entries if e.get("bucket") == "avoid"]

        for left in prefers:
            for right in avoids:
                if SelfModel._values_semantically_conflict(left.get("value", ""), right.get("value", "")):
                    contradictions.append({
                        "kind": "self_model_internal",
                        "left": left,
                        "right": right,
                        "reason": "prefer/avoid widersprechen sich",
                    })

        try:
            mem = memory
            if mem is None:
                from memory import get_memory

                mem = get_memory()
        except Exception as exc:
            log.debug("Contradiction memory lookup skipped: %s", exc)
            return contradictions[:12]

        for entry in self.relevant_preferences(limit=12, min_confidence=0.6):
            fact_key = self._preference_fact_key(entry)
            record = mem.get_fact_record(fact_key)
            if not record:
                continue
            mem_value = (record.get("value") or "").strip()
            pref_value = str(entry.get("value") or "").strip()
            if (
                mem_value
                and pref_value
                and SelfModel._values_semantically_conflict(pref_value, mem_value)
            ):
                contradictions.append({
                    "kind": "self_model_vs_memory",
                    "preference": entry,
                    "fact_key": fact_key,
                    "memory_value": mem_value,
                    "reason": "Self-Model-Präferenz widerspricht Memory-Fakt",
                })

        memory_facts = {}
        try:
            memory_facts = mem.all_facts()
        except Exception as exc:
            log.debug("Contradiction all_facts skipped: %s", exc)

        for avoid in avoids:
            avoid_value = str(avoid.get("value") or "").strip()
            if not avoid_value:
                continue
            avoid_norm = self._normalize_compare_value(avoid_value)
            for fact_key, fact_value in memory_facts.items():
                lowered_key = (fact_key or "").lower()
                if not (
                    lowered_key.startswith("pref.")
                    or lowered_key.startswith("definition.")
                ):
                    continue
                if self._normalize_compare_value(fact_value) == avoid_norm:
                    contradictions.append({
                        "kind": "avoid_vs_memory_fact",
                        "avoid": avoid,
                        "fact_key": fact_key,
                        "memory_value": fact_value,
                        "reason": "vermiedene Präferenz ist als Fakt gespeichert",
                    })
                elif self._values_semantically_conflict(avoid_value, fact_value):
                    contradictions.append({
                        "kind": "avoid_conflicts_memory_fact",
                        "avoid": avoid,
                        "fact_key": fact_key,
                        "memory_value": fact_value,
                        "reason": "avoid widerspricht Memory-Fakt",
                    })

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in contradictions:
            signature = json.dumps(
                {
                    "kind": item.get("kind"),
                    "fact_key": item.get("fact_key"),
                    "left": (item.get("left") or item.get("preference") or {}).get("value"),
                    "right": (item.get("right") or item.get("avoid") or {}).get("value"),
                    "memory_value": item.get("memory_value"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if signature in seen:
                continue
            seen.add(signature)
            deduped.append(item)
        return deduped[:12]


_model: Optional[SelfModel] = None


def get_self_model() -> SelfModel:
    global _model
    if _model is None:
        _model = SelfModel()
    return _model
