from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from executor import Executor, Strategy, Task, TaskStatus, TaskType, get_executor
from isaac_core import Intent, IsaacKernel, detect_intent
from low_complexity import (
    InteractionClass,
    classify_interaction_result,
    is_lightweight_local_class,
    local_class_response,
)
from logic import QualityScore
from memory import get_memory
from tool_policy import ToolDecisionReason


def _routing_expectations() -> list[dict]:
    return [
        {
            "id": "A",
            "input": "Hallo Isaac",
            "lightweight_local": True,
            "intent": Intent.CHAT,
            "allow_tools": False,
            "tool_eligible": False,
        },
        {
            "id": "B",
            "input": "Danke",
            "lightweight_local": True,
            "intent": Intent.CHAT,
            "allow_tools": False,
            "tool_eligible": False,
        },
        {
            "id": "C",
            "input": "Was ist 2+2?",
            "interaction_class": InteractionClass.NORMAL_CHAT,
            "intent": Intent.CHAT,
            "allow_tools": False,
            "tool_eligible": False,
        },
        {
            "id": "D",
            "input": "Erkläre mir das Wetter als sprachliches Motiv in Literatur",
            "interaction_class": InteractionClass.NORMAL_CHAT,
            "intent": Intent.CHAT,
            "allow_tools": False,
            "tool_eligible": False,
        },
        {
            "id": "E",
            "input": "Suche: Wetter Berlin",
            "interaction_class": InteractionClass.TOOL_REQUEST,
            "intent": Intent.SEARCH,
            "allow_tools": True,
            "tool_eligible": True,
        },
        {
            "id": "F",
            "input": "Browser auf GitHub",
            "interaction_class": InteractionClass.TOOL_REQUEST,
            "intent": Intent.BROWSER,
            "allow_tools": False,
            "tool_eligible": False,
        },
        {
            "id": "G",
            "input": "Und?",
            "interaction_class": InteractionClass.NORMAL_CHAT,
            "intent": Intent.CHAT,
            "allow_tools": False,
            "tool_eligible": False,
        },
    ]


def _evaluate_routing_case(case: dict) -> dict:
    text = case["input"]
    classification = classify_interaction_result(text)
    interaction_class = classification.interaction_class
    detected = detect_intent(text)
    kernel = object.__new__(IsaacKernel)
    intent = kernel._resolve_intent_from_classification(
        text, detected, interaction_class
    )
    strategy = kernel._select_response_strategy(
        user_input=text,
        intent=intent,
        interaction_class=interaction_class,
        retrieval_ctx={},
    )
    executor = object.__new__(Executor)
    task = Task(
        id=f"replay_{case['id']}",
        typ=TaskType.SEARCH if intent == Intent.SEARCH else TaskType.CHAT,
        prompt=text,
        beschreibung=text,
        strategy=strategy,
        interaction_class=interaction_class,
        classification=classification,
    )
    eligibility = executor._evaluate_tool_eligibility(task, text, iteration=0)

    checks = {
        "intent": intent == case["intent"],
        "allow_tools": strategy.allow_tools == case["allow_tools"],
        "tool_eligible": eligibility.eligible == case["tool_eligible"],
    }
    if case.get("lightweight_local"):
        checks["lightweight_local"] = is_lightweight_local_class(interaction_class)
        checks["local_response"] = bool(local_class_response(interaction_class, text))
    if case.get("interaction_class"):
        checks["interaction_class"] = interaction_class == case["interaction_class"]

    ok = all(checks.values())
    return {
        "name": f"routing_{case['id']}",
        "ok": ok,
        "detail": {
            "input": text,
            "interaction_class": interaction_class,
            "intent": intent,
            "allow_tools": strategy.allow_tools,
            "eligible": eligibility.eligible,
            "eligible_reason": eligibility.reason.value,
            "checks": checks,
        },
    }


async def _run_checkpoint_replay() -> list[dict]:
    from unittest.mock import patch

    exe = get_executor()
    mem = get_memory()
    tid = "eval_replay_evaluating"
    task = Task(id=tid, typ=TaskType.CHAT, prompt="resume me", beschreibung="resume me")
    task.status = TaskStatus.RESUMABLE
    exe._tasks[tid] = task
    mem.save_task_checkpoint(
        tid,
        "evaluating",
        input_snapshot={
            "task_id": tid,
            "typ": "chat",
            "prompt": "resume me",
            "iteration": 0,
            "status": "evaluating",
        },
        result_snapshot={
            "answer_preview": "kurze Antwort",
            "answer_full": "kurze Antwort mit genug Inhalt für eine akzeptable Bewertung.",
            "provider": "test-provider",
        },
    )
    good_score = QualityScore(total=9.0)
    with patch.object(exe.logic, "evaluate", return_value=good_score):
        action = await exe._resume_from_checkpoint(task)
    return [
        {
            "name": "resume_from_evaluating",
            "ok": action == "done" and task.status == TaskStatus.DONE,
            "detail": {"action": action, "status": task.status.value},
        },
        {
            "name": "resume_completed_state",
            "ok": task.status in {TaskStatus.DONE, TaskStatus.FAILED},
            "detail": task.status.value,
        },
    ]


def _evaluation_trace_cases() -> list[dict]:
    """Evolution 2.0: Evaluation-/Learning-Phasen sind serialisierbar und sichtbar."""
    from decision_trace import DecisionTrace, TracePhase

    trace = DecisionTrace()
    trace.add(TracePhase.CLASSIFICATION, "classified", {"class": "NORMAL_CHAT"})
    trace.add(TracePhase.EVALUATION, "quality_scored", {"score_total": 7.5, "acceptable": True})
    trace.add(TracePhase.LEARNING, "procedure_recorded", {"signature": "abcd1234"})
    phases = [e["phase"] for e in trace.to_list()]
    events = [e["event"] for e in trace.to_list()]
    return [
        {
            "name": "decision_trace_has_evaluation_phase",
            "ok": "evaluation" in phases and "quality_scored" in events,
            "detail": {"phases": phases, "events": events},
        },
        {
            "name": "decision_trace_has_learning_phase",
            "ok": "learning" in phases and "procedure_recorded" in events,
            "detail": {"phases": phases},
        },
    ]


def run() -> dict:
    cases = [_evaluate_routing_case(case) for case in _routing_expectations()]
    cases.extend(asyncio.run(_run_checkpoint_replay()))
    cases.extend(_evaluation_trace_cases())
    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "replay", "passed": passed, "total": len(cases), "cases": cases}


if __name__ == "__main__":
    import json

    print(json.dumps(run(), ensure_ascii=False, indent=2))