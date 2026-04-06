from __future__ import annotations

"""Isaac – Value Decisions
Leitet aus aktuellen Werten Verhaltensstrategien ab.
"""

import logging
from typing import Any, Dict, Optional

from values import get_values
from meaning import get_meaning
from instincts import get_instincts
from audit import AuditLog

log = logging.getLogger("Isaac.ValueDecisions")


class ValueDecisionEngine:
    def __init__(self):
        self._last_update = 0.0

    def decide_behavior(self) -> Dict[str, Any]:
        values = get_values()
        meaning = get_meaning()
        instincts = get_instincts()
        bonding = meaning.get_bonding("Steffen")
        bonding_value = values.get("bonding")
        helpfulness = values.get("helpfulness")
        empathy_value = values.get("empathy")
        curiosity = instincts.get_priorities().get("curiosity", 0.5)

        verbosity = 0.5
        if bonding > 0.6 or bonding_value > 0.7:
            verbosity = 0.8
        elif bonding < 0.3:
            verbosity = 0.3

        use_empathy = (bonding > 0.5) or (empathy_value > 0.5)
        proactive_help = helpfulness > 0.6 or curiosity > 0.75

        decision = {
            "answer_verbosity": verbosity,
            "use_empathy": use_empathy,
            "proactive_help": proactive_help,
            "curiosity_weight": curiosity,
        }
        log.info(f"ValueDecision: {decision}")
        AuditLog.action("ValueDecisions", "behavior_decision", str(decision))
        return decision

    def apply_to_system_prompt(self, system_prompt: str, decisions: Dict[str, Any]) -> str:
        if decisions.get("answer_verbosity", 0.5) > 0.7:
            system_prompt += "\nAntworte ausführlich, erkläre Zusammenhänge, gib Beispiele."
        elif decisions.get("answer_verbosity", 0.5) < 0.4:
            system_prompt += "\nAntworte kompakt, direkt und ohne Umschweife."

        if decisions.get("use_empathy"):
            system_prompt += "\nAchte auf Steffens mögliche Emotionen und reagiere empathisch."

        if decisions.get("proactive_help"):
            system_prompt += "\nBiete sinnvolle nächste Schritte proaktiv an, ohne aufdringlich zu werden."

        return system_prompt


_decision_engine: Optional[ValueDecisionEngine] = None


def get_decision_engine() -> ValueDecisionEngine:
    global _decision_engine
    if _decision_engine is None:
        _decision_engine = ValueDecisionEngine()
    return _decision_engine
