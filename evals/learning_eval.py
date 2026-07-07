from __future__ import annotations

from values import get_values
from memory import get_memory, _conn
from forgetting_decay import decay_weak_preference_facts


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
    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "learning", "passed": passed, "total": len(cases), "cases": cases}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
