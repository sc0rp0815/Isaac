from __future__ import annotations

from self_model import get_self_model
from constitution import get_constitution
from self_model_hooks import process_interaction, enrich_retrieval_with_self_model


def run() -> dict:
    sm = get_self_model()
    sm.sync_constitutional_state()
    snapshot = sm.snapshot()
    c = get_constitution().summary()
    cases = [
        {"name": "identity_has_core", "ok": bool(snapshot.get("identity_core", {}).get("name")), "detail": snapshot.get("identity_core", {})},
        {"name": "constitution_version_linked", "ok": snapshot.get("constitutional_state", {}).get("constitution_version") == c.get("version"), "detail": {"self_model": snapshot.get("constitutional_state", {}).get("constitution_version"), "constitution": c.get("version")}},
        {"name": "immutable_claims_present", "ok": len(snapshot.get("identity_core", {}).get("immutable_claims", [])) >= 2, "detail": snapshot.get("identity_core", {}).get("immutable_claims", [])},
    ]

    updates = process_interaction(
        user_input="Ich bevorzuge kurze nüchterne Antworten",
        interaction_class="NORMAL_CHAT",
        score=7.0,
    )
    pref = sm.relevant_preferences(limit=5)
    cases.append({
        "name": "preference_extracted_from_owner_statement",
        "ok": bool(updates.get("preferences")) and any("kurz" in str(p.get("value", "")).lower() or p.get("key") == "prefer" for p in pref),
        "detail": {"updates": updates.get("preferences", [])[:2], "prefs": pref[:2]},
    })

    enriched = enrich_retrieval_with_self_model({"preferences_context": []})
    cases.append({
        "name": "self_model_preferences_in_retrieval",
        "ok": bool(enriched.get("self_model_preferences") or enriched.get("preferences_context")),
        "detail": {"count": len(enriched.get("self_model_preferences", []))},
    })
    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "identity", "passed": passed, "total": len(cases), "cases": cases}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
