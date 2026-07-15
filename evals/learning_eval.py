from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from values import get_values
from memory import get_memory, _conn
from forgetting_decay import decay_weak_preference_facts


def _procedure_degrade_cases() -> list[dict]:
    """Procedure-Memory: Fehlschläge senken Reliability und degradieren."""
    from types import SimpleNamespace
    from procedure_memory import record_task_outcome
    from tool_runtime import _procedure_hints_for_prompt
    from memory import get_memory

    mem = get_memory()
    unique = f"e2proc{id(object())}"
    tool_name = f"isaac.e2_unique_{unique}"
    score = SimpleNamespace(total=2.0)
    task = SimpleNamespace(
        id=f"task_{unique}",
        typ=SimpleNamespace(value="search"),
        prompt=f"Suche {unique} marker",
        beschreibung=f"Suche {unique} marker",
        used_tools=[{"name": tool_name}],
        score=score,
        status=SimpleNamespace(value="failed"),
        classification=SimpleNamespace(normalized_text=f"suche {unique}"),
        decision_trace=None,
    )
    first = record_task_outcome(task)
    degraded = bool((first or {}).get("degraded"))
    # Explizit degraded Procedure mit einzigartigem Tool — darf nicht boosten
    sig = f"e2degrade{unique}"[:16]
    mem.upsert_procedure(
        signature=sig,
        task_type="search",
        intent_hint=f"marker {unique}",
        keywords=[unique, "marker", "suche"],
        tools_used=[tool_name],
        reliability=0.95,
        success_count=0,
        failure_count=4,
        last_status="failed",
        degraded=True,
    )
    hints = _procedure_hints_for_prompt(f"Suche marker {unique}")
    skipped = tool_name not in hints
    return [
        {
            "name": "procedure_failure_marks_degraded",
            "ok": bool(first) and degraded,
            "detail": {"first": first},
        },
        {
            "name": "degraded_procedure_skipped_in_hints",
            "ok": skipped,
            "detail": {"tool": tool_name, "hints": hints, "signature": sig},
        },
    ]


def _regelwerk_memory_cases() -> list[dict]:
    from regelwerk import Frage
    from isaac_core import IsaacKernel

    kernel = object.__new__(IsaacKernel)
    frage = Frage(
        id="F-eval-learning",
        text="Was meinst du genau mit 'Status'? Für zukünftige Anfragen wichtig.",
        kontext="eval",
        prioritaet=0.5,
    )
    saved_facts: list[tuple[str, str]] = []

    kernel.regelwerk = SimpleNamespace(
        beantworte_frage=lambda fid, text: setattr(frage, "beantwortet", True),
        build_answer_ack=lambda fid, text: f"Verstanden: {text}",
        analysiere=lambda *args, **kwargs: [],
        get_pending_frage=lambda: None,
        get_top_pending_frage=lambda: None,
        get_frage=lambda fid: frage if fid == "F-eval-learning" else None,
        _extract_term_from_frage=lambda f: "Status",
    )
    kernel.memory = SimpleNamespace(
        set_fact=lambda key, value, **kwargs: saved_facts.append((key, value)) or True
    )
    kernel._background = None
    kernel._awaiting_frage_id = "F-eval-learning"
    kernel.empathie = SimpleNamespace(
        analysiere=lambda text: SimpleNamespace(
            node=SimpleNamespace(zustand="neutral"),
            interface_fehler="",
        )
    )

    answer = "Status meint bei mir den Systemzustand aller Module."
    result = asyncio.run(kernel.process(answer))
    persist_ok = ("definition.status", answer) in saved_facts

    mem = get_memory()
    unique = f"eval_learning_def_{id(saved_facts)}"
    mem.set_fact(f"definition.{unique}", answer, source="owner", confidence=0.95)
    retrieval = mem.build_retrieval_context(
        user_input=f"Was bedeutet {unique}?",
        intent="chat",
        interaction_class="NORMAL_CHAT",
        n_history=3,
    ).as_dict()
    surfaced = any(
        f.get("key") == f"definition.{unique}"
        for f in retrieval.get("relevant_facts", [])
    )

    return [
        {
            "name": "regelwerk_answer_persists_definition_fact",
            "ok": persist_ok and "Verstanden" in result,
            "detail": {"saved": saved_facts, "result": result[:80]},
        },
        {
            "name": "definition_fact_surfaces_in_retrieval",
            "ok": surfaced,
            "detail": {
                "key": f"definition.{unique}",
                "facts": [f.get("key") for f in retrieval.get("relevant_facts", [])[:5]],
            },
        },
    ]


def run() -> dict:
    vals = get_values()
    mem = get_memory()
    before = vals.get("patience", 0.5)
    vals.update("patience", 1.0, "repeated positive feedback for calm responses", repetition=1.5, consistency=1.0, relevance=0.9)
    after = vals.get("patience", 0.5)
    dev = mem.recent_development_events(10)

    decay_key = "eval_pref_decay_marker"
    mem.set_fact(decay_key, "test_value", source="inferred", confidence=0.5)
    with _conn() as con:
        con.execute(
            "UPDATE facts SET updated=? WHERE key=?",
            ("2020-01-01 00:00:00", decay_key),
        )
    decay_changes = decay_weak_preference_facts(mem)
    decay_ok = any(c.get("key") == decay_key for c in decay_changes)

    contradict_key = "eval_contradict_marker"
    mem.set_fact(contradict_key, "alpha", source="inferred", confidence=0.7)
    mem.set_fact(contradict_key, "beta", source="inferred", confidence=0.7)
    contradict_conf = float((mem.get_fact_record(contradict_key) or {}).get("confidence", 1.0))
    contradict_ok = contradict_conf < 0.7

    archive_id = mem.log_development_event(
        event_type="eval_archive_probe",
        target_kind="eval",
        target_key="archive_probe",
        reason="eval archive test",
    )
    with _conn() as con:
        con.execute(
            "UPDATE development_events SET ts=? WHERE id=?",
            ("2019-06-01 00:00:00", archive_id),
        )
    for i in range(8):
        mem.log_development_event(
            event_type="eval_filler",
            target_kind="eval",
            target_key=f"filler_{i}",
            reason="eval filler",
        )
    archived_count = mem.archive_development_events(older_than_days=30, keep_recent=5)
    archive_ok = archived_count >= 1 and any(
        e.get("id") == archive_id for e in mem.recent_archived_development_events(20)
    )

    cases = [
        {"name": "value_updates_are_bounded", "ok": (after - before) <= 0.26, "detail": {"before": before, "after": after}},
        {"name": "development_log_written", "ok": any(e.get("target_key") == "patience" for e in dev), "detail": dev[:3]},
        {"name": "weak_preference_decays", "ok": decay_ok, "detail": decay_changes[:2]},
        {"name": "contradicted_fact_degrades", "ok": contradict_ok, "detail": {"confidence": contradict_conf}},
        {"name": "development_events_archived", "ok": archive_ok, "detail": {"archived": archived_count}},
    ]
    cases.extend(_regelwerk_memory_cases())
    cases.extend(_procedure_degrade_cases())
    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "learning", "passed": passed, "total": len(cases), "cases": cases}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
