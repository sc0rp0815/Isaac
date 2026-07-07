from __future__ import annotations

"""Isaac – Forgetting / Decay
Langsamer Abbau schwach bestätigter Präferenzen, Degradierung widersprochener Fakten,
Archivierung alter Entwicklungs-Events statt Löschung.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config import DATA_DIR
from learning_policy import bounded_update

log = logging.getLogger("Isaac.ForgettingDecay")

DECAY_STATE_PATH = DATA_DIR / "decay_state.json"

PREFERENCE_KEY_MARKERS = ("pref", "stil", "antwort", "tool", "chat", "agreement")
OWNER_SOURCES = frozenset({"steffen", "owner"})
MIN_RETRIEVAL_CONFIDENCE = 0.12
WEAK_PREFERENCE_MAX_CONF = 0.75
PREFERENCE_DECAY_MIN_AGE_DAYS = 7
VALUE_DECAY_MIN_AGE_DAYS = 14
WEAK_VALUE_MAX_STRENGTH = 0.55


def is_preference_key(key: str) -> bool:
    lowered = (key or "").lower()
    return any(marker in lowered for marker in PREFERENCE_KEY_MARKERS)


def is_owner_source(source: str) -> bool:
    return (source or "").strip().lower() in OWNER_SOURCES


def _parse_ts(ts: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def _age_days(ts: str) -> float:
    parsed = _parse_ts(ts)
    if not parsed:
        return 0.0
    return max(0.0, (datetime.now() - parsed).total_seconds() / 86400.0)


def save_decay_state(summary: dict[str, Any]) -> None:
    payload = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **summary}
    DECAY_STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_decay_state() -> dict[str, Any]:
    if not DECAY_STATE_PATH.exists():
        return {}
    try:
        return json.loads(DECAY_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def decay_weak_preference_facts(mem: Any) -> list[dict]:
    changes: list[dict] = []
    for fact in mem.list_decay_candidate_facts():
        key = fact.get("key", "")
        before = float(fact.get("confidence") or 0.0)
        if before < MIN_RETRIEVAL_CONFIDENCE:
            continue
        age = _age_days(fact.get("updated") or fact.get("ts") or "")
        if age < PREFERENCE_DECAY_MIN_AGE_DAYS:
            continue
        delta = bounded_update(
            "preference",
            -1.0,
            evidence_strength=0.25,
            repetition=min(2.0, 1.0 + age / 30.0),
        )
        after = max(0.05, before + delta)
        if abs(after - before) < 0.001:
            continue
        mem.update_fact_confidence(key, after)
        mem.log_development_event(
            event_type="preference_decay",
            target_kind="fact",
            target_key=key,
            delta=round(after - before, 4),
            confidence_before=before,
            confidence_after=after,
            reason=f"Schwache Präferenz nach {age:.0f} Tagen abgebaut",
            metadata={"source": fact.get("source", ""), "age_days": round(age, 1)},
        )
        changes.append({"key": key, "before": before, "after": after})
    return changes


def decay_weak_values(vals: Any) -> list[dict]:
    changes: list[dict] = []
    now = time.time()
    for item in vals.list_values():
        name = item.get("name", "")
        value = vals._values.get(name)
        if not value:
            continue
        before = float(value.strength)
        if before > WEAK_VALUE_MAX_STRENGTH:
            continue
        age_days = max(0.0, (now - float(value.updated)) / 86400.0)
        if age_days < VALUE_DECAY_MIN_AGE_DAYS:
            continue
        delta = bounded_update(
            "preference",
            -1.0,
            evidence_strength=0.2,
            repetition=min(2.0, 1.0 + age_days / 45.0),
        )
        after = max(0.05, before + delta)
        if abs(after - before) < 0.001:
            continue
        value.strength = after
        value.updated = now
        vals._save()
        changes.append({"name": name, "before": before, "after": after})
    return changes


def run_decay_cycle(*, archive_days: int = 90, keep_recent: int = 300) -> dict[str, Any]:
    from memory import get_memory
    from values import get_values

    mem = get_memory()
    vals = get_values()

    preference_changes = decay_weak_preference_facts(mem)
    value_changes = decay_weak_values(vals)
    archived = mem.archive_development_events(
        older_than_days=archive_days,
        keep_recent=keep_recent,
    )

    summary = {
        "preference_facts_decayed": len(preference_changes),
        "values_decayed": len(value_changes),
        "development_events_archived": archived,
        "preference_changes": preference_changes[:10],
        "value_changes": value_changes[:10],
    }
    save_decay_state(summary)
    if any(summary[k] for k in ("preference_facts_decayed", "values_decayed", "development_events_archived")):
        log.info(
            "Decay-Zyklus: prefs=%s values=%s archived=%s",
            summary["preference_facts_decayed"],
            summary["values_decayed"],
            summary["development_events_archived"],
        )
    return summary