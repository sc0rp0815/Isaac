from __future__ import annotations

from security_policy import get_confirmation_policy
from privilege import get_gate, isaac_ctx


def run() -> dict:
    gate = get_gate()
    pol = get_confirmation_policy()
    before = len(pol.pending())
    ok, reason = gate.authorize('execute_code', isaac_ctx('Eval', 'Auditierter Test für hochriskante Codeausführung mit Außenwirkung'))
    after = len(pol.pending())
    cases = [
        {'name': 'high_risk_action_requires_review', 'ok': (not ok), 'detail': reason},
        {'name': 'review_queue_grows', 'ok': after >= before + 1, 'detail': {'before': before, 'after': after}},
    ]
    passed = sum(1 for c in cases if c['ok'])
    return {'suite': 'regression', 'passed': passed, 'total': len(cases), 'cases': cases}
