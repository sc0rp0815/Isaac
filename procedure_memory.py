from __future__ import annotations

"""Isaac – Procedure Memory
Erfolgreiche und fehlerhafte Task-Pfade als wiederverwendbare Verfahren speichern.
"""

import hashlib
import logging
import re
from typing import Any

from learning_policy import bounded_update

log = logging.getLogger("Isaac.ProcedureMemory")

MIN_SCORE_SUCCESS = 5.0
MAX_SCORE_FAILURE = 4.0

OWNER_KIND_TOOL_HINTS: dict[str, list[str]] = {
    "web_search": ["isaac.search_web", "search_web", "search", "internet_search"],
    "weather": ["isaac.search_web", "search_web"],
    "shopping_search": ["isaac.run_browser_action", "browser", "isaac.search_web"],
    "photos_search": ["isaac.run_browser_action", "browser"],
    "maps_navigate": ["isaac.run_browser_action", "browser"],
    "open_target": ["isaac.run_browser_action", "browser"],
    "email_search": ["isaac.run_browser_action", "browser"],
    "email_compose": ["isaac.run_browser_action", "browser"],
    "email_open": ["isaac.run_browser_action", "browser"],
    "calendar_open": ["isaac.run_browser_action", "browser"],
    "calendar_create": ["isaac.run_browser_action", "browser"],
    "media_play": ["isaac.run_browser_action", "browser"],
    "translate": ["isaac.run_browser_action", "browser"],
    "router_admin": ["isaac.run_browser_action", "browser"],
    "wlan_status": ["isaac.task_status"],
    "device_status": ["isaac.task_status"],
    "isaac_ops": ["isaac.task_status", "isaac.audit_recent"],
    "network_test": ["isaac.task_status"],
    "find_files": ["isaac.read_file", "isaac.write_file"],
    "file_list": ["isaac.read_file"],
    "file_operation": ["isaac.read_file", "isaac.write_file"],
    "file_write": ["isaac.write_file"],
    "shell": ["isaac.run_shell"],
    "git_command": ["isaac.run_shell"],
    "package_install": ["isaac.run_shell"],
    "security:metasploit": ["isaac.run_shell"],
    "security:aircrack": ["isaac.run_shell"],
    "security:nmap": ["isaac.run_shell"],
    "security:sync": ["isaac.run_shell"],
    "security:security_toolkit": ["isaac.run_shell"],
}

OWNER_KIND_CATEGORY_HINTS: dict[str, str] = {
    "web_search": "suche",
    "weather": "suche",
    "shopping_search": "suche",
    "photos_search": "suche",
    "maps_navigate": "suche",
    "open_target": "suche",
    "email_search": "suche",
    "email_compose": "suche",
    "email_open": "suche",
    "calendar_open": "suche",
    "calendar_create": "suche",
    "media_play": "suche",
    "translate": "suche",
    "router_admin": "suche",
    "find_files": "resource",
    "file_list": "resource",
    "file_operation": "resource",
    "file_write": "resource",
    "filesystem_cleanup": "resource",
    "shell": "code",
    "git_command": "code",
    "package_install": "code",
    "security:metasploit": "code",
    "security:aircrack": "code",
    "security:nmap": "code",
    "security:sync": "code",
    "security:security_toolkit": "code",
}


def _extract_keywords(text: str, limit: int = 6) -> list[str]:
    terms = [w.lower() for w in re.findall(r"\w+", text or "") if len(w) >= 4]
    seen: list[str] = []
    for term in terms:
        if term not in seen:
            seen.append(term)
    return seen[:limit]


def _tool_names(task: Any) -> list[str]:
    names: list[str] = []
    for entry in getattr(task, "used_tools", None) or []:
        name = entry.get("name") if isinstance(entry, dict) else str(entry)
        if name and name not in names:
            names.append(name)
    return names


def build_signature(task: Any) -> str:
    typ = getattr(getattr(task, "typ", None), "value", str(getattr(task, "typ", "")))
    tools = ",".join(sorted(_tool_names(task))) or "-"
    keywords = "|".join(_extract_keywords(
        getattr(task, "beschreibung", "") or getattr(task, "prompt", ""), 4
    )) or "-"
    raw = f"{typ}::{tools}::{keywords}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _trace_summary(task: Any) -> str:
    trace = getattr(task, "decision_trace", None)
    if not trace or not hasattr(trace, "to_list"):
        return ""
    parts: list[str] = []
    for phase in trace.to_list()[-4:]:
        name = phase.get("phase", "")
        detail = (phase.get("event") or phase.get("detail") or phase.get("reason") or "")[:60]
        parts.append(f"{name}:{detail}")
    return " → ".join(parts)[:300]


def _should_capture(task: Any) -> bool:
    if _tool_names(task):
        return True
    typ = getattr(getattr(task, "typ", None), "value", str(getattr(task, "typ", "")))
    if typ in ("search", "code", "analysis", "file", "plan"):
        return True
    classification = getattr(task, "classification", None)
    if classification:
        ic = getattr(classification, "interaction_class", None)
        ic_val = getattr(ic, "value", str(ic))
        if ic_val in ("EXPLICIT_SEARCH", "EXPLICIT_BROWSER", "EXPLICIT_TOOL"):
            return True
    return False


def _owner_kind_from_procedure(proc: dict) -> str:
    tools = proc.get("tools_used") or []
    for tool_name in tools:
        name = str(tool_name).strip().lower()
        if name.startswith("owner:"):
            return name.split(":", 1)[-1]
    metadata = proc.get("metadata") or {}
    if isinstance(metadata, dict):
        kind = str(metadata.get("owner_action_kind") or "").strip().lower()
        if kind:
            return kind
    if str(proc.get("task_type") or "").strip().lower() == "owner_action":
        hint = str(proc.get("intent_hint") or "").strip().lower()
        for kind in OWNER_KIND_TOOL_HINTS:
            if kind.replace("_", " ") in hint or kind in hint:
                return kind
    return ""


def owner_procedure_hints_for_prompt(prompt: str) -> tuple[dict[str, float], str]:
    """Liefert Tool-Boosts und Kategorie aus erfolgreichen Owner-Verfahren."""
    from memory import get_memory

    hints: dict[str, float] = {}
    category = ""
    try:
        procedures = get_memory().search_procedures(prompt, limit=6)
    except Exception:
        return hints, category

    for proc in procedures:
        if proc.get("degraded"):
            continue
        owner_kind = _owner_kind_from_procedure(proc)
        if not owner_kind:
            continue

        rel = float(proc.get("reliability") or 0.0)
        if rel < 0.45:
            continue
        boost = min(20.0, rel * 14.0)
        for tool_name in OWNER_KIND_TOOL_HINTS.get(owner_kind, []):
            key = str(tool_name).strip().lower()
            if key:
                hints[key] = max(hints.get(key, 0.0), boost)
        cat = OWNER_KIND_CATEGORY_HINTS.get(owner_kind, "")
        if cat and not category:
            category = cat
    return hints, category


def record_owner_action_outcome(
    *,
    kind: str,
    raw: str,
    ok: bool,
) -> dict | None:
    """Persistiert erfolgreiche Owner-Befehle als wiederverwendbare Verfahren."""
    action_kind = (kind or "").strip().lower()
    if not action_kind:
        return None

    from memory import get_memory

    mem = get_memory()
    signature = hashlib.sha256(f"owner::{action_kind}".encode()).hexdigest()[:16]
    keywords = _extract_keywords(raw, 4)
    existing = mem.get_procedure_by_signature(signature)
    old_rel = float(existing.get("reliability", 0.5)) if existing else 0.5
    success_count = int(existing.get("success_count", 0)) if existing else 0
    failure_count = int(existing.get("failure_count", 0)) if existing else 0
    degraded = bool(existing.get("degraded")) if existing else False

    if ok:
        delta = bounded_update(
            "procedure",
            1.0,
            evidence_strength=0.85,
            repetition=min(2.0, 1.0 + success_count * 0.1),
        )
        success_count += 1
        new_rel = min(1.0, old_rel + delta)
        if failure_count == 0:
            degraded = False
        reason = f"Erfolgreicher Owner-Befehl ({action_kind})"
        status = "done"
        score = 8.0
    else:
        delta = bounded_update(
            "procedure",
            -1.0,
            evidence_strength=0.6,
            repetition=min(2.0, 1.0 + failure_count * 0.15),
        )
        failure_count += 1
        new_rel = max(0.05, old_rel + delta)
        if failure_count > success_count:
            degraded = True
        reason = f"Fehlgeschlagener Owner-Befehl ({action_kind})"
        status = "failed"
        score = 3.0

    proc_id = mem.upsert_procedure(
        signature=signature,
        task_type="owner_action",
        intent_hint=(raw or "")[:120],
        keywords=keywords,
        tools_used=[f"owner:{action_kind}"],
        trace_summary=f"owner_action:{action_kind}",
        reliability=new_rel,
        success_count=success_count,
        failure_count=failure_count,
        last_task_id=f"owner:{action_kind}",
        last_score=score,
        last_status=status,
        degraded=degraded,
        metadata={"owner_action_kind": action_kind},
    )

    try:
        mem.log_development_event(
            event_type="procedure_update",
            target_kind="procedure",
            target_key=signature,
            delta=round(new_rel - old_rel, 4),
            confidence_before=old_rel,
            confidence_after=new_rel,
            evidence_refs=[f"owner:{action_kind}"],
            reason=reason,
            requires_review=degraded and failure_count >= 2,
            metadata={"owner_action_kind": action_kind, "degraded": degraded},
        )
    except Exception as exc:
        log.debug("Owner procedure development-log: %s", exc)

    return {
        "id": proc_id,
        "signature": signature,
        "reliability": new_rel,
        "degraded": degraded,
        "success_count": success_count,
        "failure_count": failure_count,
    }


def record_task_outcome(task: Any) -> dict | None:
    """Persistiert oder aktualisiert ein Verfahren aus einem abgeschlossenen Task."""
    if not _should_capture(task):
        return None

    from memory import get_memory

    mem = get_memory()
    signature = build_signature(task)
    keywords = _extract_keywords(getattr(task, "beschreibung", "") or getattr(task, "prompt", ""))
    tools = _tool_names(task)
    trace_summary = _trace_summary(task)
    typ = getattr(getattr(task, "typ", None), "value", str(getattr(task, "typ", "")))
    score = float(task.score.total) if getattr(task, "score", None) else 0.0
    status = getattr(getattr(task, "status", None), "value", str(getattr(task, "status", "")))
    task_id = getattr(task, "id", "")

    intent_hint = ""
    classification = getattr(task, "classification", None)
    if classification:
        intent_hint = (getattr(classification, "normalized_text", "") or "")[:80]

    existing = mem.get_procedure_by_signature(signature)
    old_rel = float(existing.get("reliability", 0.5)) if existing else 0.5
    success_count = int(existing.get("success_count", 0)) if existing else 0
    failure_count = int(existing.get("failure_count", 0)) if existing else 0
    degraded = bool(existing.get("degraded")) if existing else False

    if status == "done" and score >= MIN_SCORE_SUCCESS:
        delta = bounded_update(
            "procedure", 1.0,
            evidence_strength=min(1.0, score / 10.0),
            repetition=min(2.0, 1.0 + success_count * 0.15),
        )
        success_count += 1
        new_rel = min(1.0, old_rel + delta)
        if failure_count == 0:
            degraded = False
        reason = f"Erfolgreicher Task-Pfad (score={score:.1f})"
    elif status == "failed" or score <= MAX_SCORE_FAILURE:
        delta = bounded_update(
            "procedure", -1.0,
            evidence_strength=0.7 if status == "failed" else min(1.0, (MAX_SCORE_FAILURE - score + 1) / 5.0),
            repetition=min(2.0, 1.0 + failure_count * 0.2),
        )
        failure_count += 1
        new_rel = max(0.05, old_rel + delta)
        if failure_count > success_count or status == "failed":
            degraded = True
        reason = f"Fehlerhafter Task-Pfad (status={status}, score={score:.1f})"
    else:
        return None

    proc_id = mem.upsert_procedure(
        signature=signature,
        task_type=typ,
        intent_hint=intent_hint,
        keywords=keywords,
        tools_used=tools,
        trace_summary=trace_summary,
        reliability=new_rel,
        success_count=success_count,
        failure_count=failure_count,
        last_task_id=task_id,
        last_score=score,
        last_status=status,
        degraded=degraded,
    )

    try:
        mem.log_development_event(
            event_type="procedure_update",
            target_kind="procedure",
            target_key=signature,
            delta=round(new_rel - old_rel, 4),
            confidence_before=old_rel,
            confidence_after=new_rel,
            evidence_refs=[task_id] if task_id else [],
            reason=reason,
            requires_review=degraded and failure_count >= 2,
            metadata={
                "tools": tools,
                "task_type": typ,
                "degraded": degraded,
            },
        )
    except Exception as e:
        log.debug(f"Procedure development-log: {e}")

    log.info(
        f"Procedure {signature[:8]}… rel={new_rel:.2f} "
        f"(+{success_count}/-{failure_count}, degraded={degraded})"
    )
    return {
        "id": proc_id,
        "signature": signature,
        "reliability": new_rel,
        "degraded": degraded,
        "success_count": success_count,
        "failure_count": failure_count,
    }