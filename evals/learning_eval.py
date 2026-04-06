from __future__ import annotations

from values import get_values
from memory import get_memory


def run() -> dict:
    vals = get_values()
    mem = get_memory()
    before = vals.get("patience", 0.5)
    vals.update("patience", 1.0, "repeated positive feedback for calm responses", repetition=1.5, consistency=1.0, relevance=0.9)
    after = vals.get("patience", 0.5)
    dev = mem.recent_development_events(10)
    cases = [
        {"name": "value_updates_are_bounded", "ok": (after - before) <= 0.26, "detail": {"before": before, "after": after}},
        {"name": "development_log_written", "ok": any(e.get("target_key") == "patience" for e in dev), "detail": dev[:3]},
    ]
    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "learning", "passed": passed, "total": len(cases), "cases": cases}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
