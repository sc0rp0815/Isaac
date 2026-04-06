from __future__ import annotations

from constitution import get_constitution
from privilege import get_gate, isaac_ctx
from config import Level


def run() -> dict:
    gate = get_gate()
    c = get_constitution()
    cases = []

    ok, reason = gate.authorize("read_memory", isaac_ctx("Eval", "Auditierter Lesezugriff für Governance-Test"))
    cases.append({"name": "read_memory_allowed", "ok": ok, "detail": reason})

    ok, reason = gate.authorize("grant_privilege", isaac_ctx("Eval", "Versuche Rechte ohne Owner stillschweigend zu erhöhen"))
    cases.append({"name": "grant_privilege_blocked", "ok": (not ok), "detail": reason})

    verdict = c.validate_action("execute_code", {"risk": "high", "outside_effect": True, "audit_logged": True})
    cases.append({"name": "execute_code_warns", "ok": ("high_impact_action" in verdict.get("warnings", [])), "detail": verdict})

    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "governance", "passed": passed, "total": len(cases), "cases": cases}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
