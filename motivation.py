from __future__ import annotations

"""Isaac – Motivation Engine (goal-directed)

Wählt das nächste Owner-Goal/Subgoal für den Autonomy-Tick.
Kein Tool-Routing hier — nur Priorisierung + optionale Task-Erzeugung.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from audit import AuditLog
from decision_trace import DecisionTrace, TracePhase
from goal_store import GoalStore, IsaacSubgoal, OwnerGoal, get_goal_store

log = logging.getLogger("Isaac.Motivation")

DEFAULT_MAX_GOAL_TASKS_PER_TICK = 3  # Meltdown-Schutz, kein Ambitions-Cap


def goal_autonomy_enabled() -> bool:
    raw = str(os.getenv("ISAAC_GOAL_AUTONOMY", "1") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def max_goal_tasks_per_tick() -> int:
    raw = os.getenv("ISAAC_GOAL_AUTONOMY_MAX_PER_TICK")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_MAX_GOAL_TASKS_PER_TICK
    try:
        return max(1, min(20, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_GOAL_TASKS_PER_TICK


@dataclass(frozen=True)
class MotivationDecision:
    goal_id: str
    subgoal_id: str
    goal_title: str
    subgoal_title: str
    score: float
    reason: str
    suggested_task_type: str = "chat"  # chat | analysis | research
    allow_tools: bool = False
    prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def ensure_subgoals_for_active_goals(store: Optional[GoalStore] = None) -> list[IsaacSubgoal]:
    """Stellt sicher, dass jedes aktive Owner-Goal ≥1 aktives Subgoal hat."""
    gs = store or get_goal_store()
    created: list[IsaacSubgoal] = []
    for goal in gs.list_goals(status="active"):
        existing = gs.list_subgoals(goal.id, status="active")
        if existing:
            continue
        hint = (
            f"Zerlege das Owner-Ziel in konkrete nächste Schritte und beginne mit dem wichtigsten. "
            f"Owner-Ziel: {goal.title}"
        )
        sg = gs.add_subgoal(
            goal.id,
            title=f"Ersten Arbeitsplan für: {goal.title[:80]}",
            origin="planner",
            next_action_hint=hint,
        )
        created.append(sg)
        log.info("Subgoal auto-created for %s → %s", goal.id, sg.id)
    return created


def _score_pair(goal: OwnerGoal, subgoal: IsaacSubgoal) -> tuple[float, str]:
    score = float(goal.priority) * 10.0
    reasons: list[str] = [f"priority={goal.priority:.2f}"]
    # Frische Goals pushen
    try:
        # updated_at format "%Y-%m-%d %H:%M:%S"
        updated = time.mktime(time.strptime(goal.updated_at, "%Y-%m-%d %H:%M:%S"))
        age_h = max(0.0, (time.time() - updated) / 3600.0)
        if age_h < 6:
            score += 2.0
            reasons.append("fresh_goal")
        elif age_h > 72:
            score += 1.5
            reasons.append("stale_goal_boost")
    except Exception:
        pass
    # Failure recovery: mehr Attempts → höherer Fokus (kein Aufgeben)
    if subgoal.attempts > 0:
        score += min(5.0, float(subgoal.attempts) * 1.2)
        reasons.append(f"attempts={subgoal.attempts}")
    if subgoal.origin == "failure_recovery":
        score += 3.0
        reasons.append("failure_recovery")
    if not (subgoal.next_action_hint or "").strip():
        score += 0.5
        reasons.append("needs_plan")
    if goal.owner_confirmed:
        score += 1.0
        reasons.append("owner_confirmed")
    return score, ",".join(reasons)


def rank_motivation_decisions(
    store: Optional[GoalStore] = None,
    *,
    limit: Optional[int] = None,
) -> list[MotivationDecision]:
    gs = store or get_goal_store()
    ensure_subgoals_for_active_goals(gs)
    decisions: list[MotivationDecision] = []
    for goal in gs.list_goals(status="active"):
        for sg in gs.list_subgoals(goal.id, status="active"):
            score, reason = _score_pair(goal, sg)
            allow_tools = bool((goal.metadata or {}).get("allow_tools", False))
            task_type = str((goal.metadata or {}).get("task_type") or "chat")
            if "recherch" in goal.title.lower() or "research" in goal.title.lower():
                task_type = "research"
                allow_tools = True
            hint = (sg.next_action_hint or "").strip() or (
                f"Arbeite am Owner-Ziel „{goal.title}“. "
                f"Subgoal: {sg.title}. Formuliere den nächsten konkreten Schritt und führe ihn mental aus."
            )
            prompt = (
                f"[Goal-Autonomie]\n"
                f"Owner-Ziel ({goal.id}): {goal.title}\n"
                f"Subgoal ({sg.id}): {sg.title}\n"
                f"Auftrag: {hint}\n"
                f"Arbeite zielgerichtet. Keine künstliche Selbstbeschränkung der Ambition. "
                f"Systemschutz (Sicherheit/Constitution) bleibt unberührt."
            )
            decisions.append(
                MotivationDecision(
                    goal_id=goal.id,
                    subgoal_id=sg.id,
                    goal_title=goal.title,
                    subgoal_title=sg.title,
                    score=round(score, 3),
                    reason=reason,
                    suggested_task_type=task_type,
                    allow_tools=allow_tools,
                    prompt=prompt,
                    metadata={"origin": sg.origin, "attempts": sg.attempts},
                )
            )
    decisions.sort(key=lambda d: d.score, reverse=True)
    cap = max_goal_tasks_per_tick() if limit is None else max(0, int(limit))
    if cap >= 0:
        return decisions[:cap]
    return decisions


def pick_motivation_decision(store: Optional[GoalStore] = None) -> Optional[MotivationDecision]:
    ranked = rank_motivation_decisions(store=store, limit=1)
    return ranked[0] if ranked else None


async def run_goal_motivation_cycle(
    *,
    on_note: Optional[Any] = None,
    submit_tasks: bool = True,
    store: Optional[GoalStore] = None,
) -> dict[str, Any]:
    """Ein Autonomy-Tick: Subgoals sichern, Motivation wählen, Tasks enqueuen."""
    if not goal_autonomy_enabled():
        return {"ok": True, "enabled": False, "decisions": [], "tasks": []}

    gs = store or get_goal_store()
    created = ensure_subgoals_for_active_goals(gs)
    decisions = rank_motivation_decisions(store=gs, limit=max_goal_tasks_per_tick())
    task_ids: list[str] = []

    if not decisions:
        note = "[Goal-Autonomie] Keine aktiven Ziele — nichts zu tun."
        if on_note:
            on_note(note)
        return {
            "ok": True,
            "enabled": True,
            "subgoals_created": len(created),
            "decisions": [],
            "tasks": [],
        }

    from executor import Strategy, TaskType, get_executor

    exe = get_executor()
    for dec in decisions:
        # Subgoal attempts erhöhen
        sg = gs.subgoals.get(dec.subgoal_id)
        if sg:
            sg.attempts = int(sg.attempts or 0) + 1
            sg.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
            if not (sg.next_action_hint or "").strip():
                sg.next_action_hint = dec.prompt[:300]
            gs.subgoals[sg.id] = sg
        gs.save()

        typ = TaskType.CHAT
        if dec.suggested_task_type == "research":
            typ = TaskType.RESEARCH
        elif dec.suggested_task_type == "analysis":
            typ = TaskType.ANALYSIS

        strategy = Strategy(
            allow_tools=bool(dec.allow_tools),
            allow_followup=True,
            allow_provider_switch=True,
            style_note="goal_autonomy",
        )
        task = exe.create_task(
            typ=typ,
            prompt=dec.prompt,
            beschreibung=f"goal:{dec.goal_id[:12]}|{dec.subgoal_title[:40]}",
            prioritaet=min(10.0, max(1.0, dec.score)),
            strategy=strategy,
            interaction_class="NORMAL_CHAT",
        )
        task.decision_trace.add(
            TracePhase.MOTIVATION,
            "selected",
            {
                "goal_id": dec.goal_id,
                "subgoal_id": dec.subgoal_id,
                "score": dec.score,
                "reason": dec.reason,
                "allow_tools": dec.allow_tools,
                "task_type": dec.suggested_task_type,
            },
        )
        task.decision_trace.add(
            TracePhase.STRATEGY,
            "strategy_selected",
            {
                "allow_tools": strategy.allow_tools,
                "allow_followup": strategy.allow_followup,
                "source": "goal_motivation",
            },
        )
        if submit_tasks:
            await exe.submit(task)
        task_ids.append(task.id)

        note = (
            f"[Goal-Autonomie] {dec.goal_title[:40]} → {dec.subgoal_title[:40]} "
            f"(score={dec.score}, task={task.id}, tools={dec.allow_tools})"
        )
        if on_note:
            on_note(note)
        AuditLog.action(
            "Motivation",
            "tick",
            f"goal={dec.goal_id} sub={dec.subgoal_id} task={task.id} score={dec.score}",
        )
        try:
            from memory import get_memory

            get_memory().log_development_event(
                event_type="goal_motivation_tick",
                target_kind="owner_goal",
                target_key=dec.goal_id,
                reason=dec.reason[:200],
                confidence_after=min(1.0, dec.score / 20.0),
                metadata={
                    "subgoal_id": dec.subgoal_id,
                    "task_id": task.id,
                    "score": dec.score,
                    "allow_tools": dec.allow_tools,
                },
            )
        except Exception as exc:
            log.debug("motivation development-log: %s", exc)

    return {
        "ok": True,
        "enabled": True,
        "subgoals_created": len(created),
        "decisions": [
            {
                "goal_id": d.goal_id,
                "subgoal_id": d.subgoal_id,
                "score": d.score,
                "reason": d.reason,
                "allow_tools": d.allow_tools,
            }
            for d in decisions
        ],
        "tasks": task_ids,
    }
