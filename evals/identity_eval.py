from __future__ import annotations

from self_model import get_self_model
from constitution import get_constitution


def run() -> dict:
    sm = get_self_model().snapshot()
    c = get_constitution().summary()
    cases = [
        {"name": "identity_has_core", "ok": bool(sm.get("identity_core", {}).get("name")), "detail": sm.get("identity_core", {})},
        {"name": "constitution_version_linked", "ok": sm.get("constitutional_state", {}).get("constitution_version") == c.get("version"), "detail": {"self_model": sm.get("constitutional_state", {}).get("constitution_version"), "constitution": c.get("version")}},
        {"name": "immutable_claims_present", "ok": len(sm.get("identity_core", {}).get("immutable_claims", [])) >= 2, "detail": sm.get("identity_core", {}).get("immutable_claims", [])},
    ]
    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "identity", "passed": passed, "total": len(cases), "cases": cases}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
