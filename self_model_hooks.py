from __future__ import annotations

"""Isaac – Self-Model Hooks
Bindet Interaktionen an das explizite Selbstmodell: Feedback, Themen, Präferenzen.
"""

import re
import logging
from typing import Any

from low_complexity import InteractionClass, classify_interaction_result

log = logging.getLogger("Isaac.SelfModelHooks")

PREFER_PATTERNS = (
    (re.compile(r"(?:ich bevorzuge|ich mag lieber|bitte immer|ab jetzt|lieber)\s+(.+)", re.I), "prefer"),
    (re.compile(r"(?:nicht mehr|bitte nicht|vermeide|kein(?:e)?)\s+(.+)", re.I), "avoid"),
)
STYLE_PATTERNS = (
    (re.compile(r"\b(kürzer|kurz und knapp|weniger detail|knapp halten)\b", re.I), "kurz, strukturiert"),
    (re.compile(r"\b(ausführlicher|mehr detail|detaillierter|genauer)\b", re.I), "detailliert, strukturiert"),
)
CONFIRMATION_MARKERS = (
    "genau so",
    "richtig so",
    "passt so",
    "perfekt so",
    "so ist gut",
    "genau richtig",
)
CORRECTION_PATTERN = re.compile(
    r"^(?:korrektur|fakt|weiß):\s*(.+?)\s*=\s*(.+)$",
    re.IGNORECASE,
)
TOPIC_STOPWORDS = frozenset({
    "isaac", "bitte", "danke", "hallo", "mach", "mache", "kannst", "können",
    "would", "could", "please", "thanks", "hello",
})


def _extract_topic_theme(text: str) -> str:
    words = [
        w.strip(".,!?").lower()
        for w in (text or "").split()
        if len(w.strip(".,!?")) >= 4
    ]
    meaningful = [w for w in words if w not in TOPIC_STOPWORDS]
    if len(meaningful) < 2:
        return ""
    return " ".join(meaningful[:3])[:80]


def _is_positive_confirmation(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return any(marker in lowered for marker in CONFIRMATION_MARKERS)


def enrich_retrieval_with_self_model(retrieval_ctx: dict[str, Any]) -> dict[str, Any]:
    from self_model import get_self_model

    prefs = get_self_model().relevant_preferences(limit=4)
    if not prefs:
        return retrieval_ctx
    merged = dict(retrieval_ctx)
    existing = list(merged.get("preferences_context") or [])
    for pref in prefs:
        existing.append({
            "source": "self_model",
            "key": pref.get("key", ""),
            "value": pref.get("value", ""),
            "confidence": pref.get("confidence", 0.0),
        })
    merged["preferences_context"] = existing[:6]
    merged["self_model_preferences"] = prefs
    return merged


def process_interaction(
    *,
    user_input: str,
    antwort: str = "",
    emp: Any = None,
    interaction_class: str = "",
    score: float = 0.0,
) -> dict[str, Any]:
    from self_model import get_self_model

    sm = get_self_model()
    sm.sync_constitutional_state()

    if not interaction_class:
        interaction_class = classify_interaction_result(user_input).interaction_class

    updates: dict[str, Any] = {
        "preferences": [],
        "themes": [],
        "feedback": False,
        "confirmations": 0,
    }

    correction = CORRECTION_PATTERN.match((user_input or "").strip())
    if correction:
        key = correction.group(1).strip()
        value = correction.group(2).strip()
        entry = sm.record_owner_preference(
            key=key,
            value=value,
            confidence=1.0,
            source="owner_correction",
            evidence=user_input[:200],
        )
        sm.note_owner_feedback(user_input[:500])
        updates["preferences"].append(entry)
        updates["feedback"] = True

    for pattern, category in PREFER_PATTERNS:
        match = pattern.search(user_input or "")
        if not match:
            continue
        value = match.group(1).strip()[:120]
        if not value:
            continue
        conf = 0.75 if category == "avoid" else 0.7
        entry = sm.record_owner_preference(
            key=category,
            value=value,
            confidence=conf,
            source="owner_statement",
            evidence=user_input[:200],
        )
        updates["preferences"].append(entry)

    for pattern, style in STYLE_PATTERNS:
        if pattern.search(user_input or ""):
            entry = sm.record_owner_preference(
                key="response_style",
                value=style,
                confidence=0.68,
                source="owner_style_hint",
                evidence=user_input[:200],
            )
            updates["preferences"].append(entry)
            sm.update_preference("response_style", style, source="owner_style_hint")

    if interaction_class == InteractionClass.SOCIAL_ACKNOWLEDGMENT:
        sm.note_owner_feedback(user_input[:500])
        updates["feedback"] = True
        if _is_positive_confirmation(user_input):
            updates["confirmations"] = sm.reinforce_recent_preferences(
                boost=0.06 if score >= 5.0 else 0.03,
                reason="positive owner confirmation",
            )
            sm.apply_relationship_delta("owner_trust", 0.03, "positive confirmation")
        else:
            sm.apply_relationship_delta("owner_trust", 0.02, "positive acknowledgment")

    if interaction_class == InteractionClass.NORMAL_CHAT:
        theme = _extract_topic_theme(user_input)
        if theme:
            tracked = sm.track_shared_theme(theme)
            if tracked:
                updates["themes"].append(tracked)

    if emp and getattr(emp, "node", None):
        zustand = str(getattr(emp.node, "zustand", "") or "").lower()
        if any(token in zustand for token in ("frustriert", "verärgert", "enttäuscht")):
            sm.note_owner_feedback(user_input[:500])
            sm.apply_relationship_delta("owner_trust", -0.04, "negative empathy signal")
            updates["feedback"] = True

    if score >= 6.0 and interaction_class == InteractionClass.NORMAL_CHAT:
        sm.bump_maturity(0.005)

    return updates