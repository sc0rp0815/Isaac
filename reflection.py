from __future__ import annotations

"""Isaac – Reflection Engine
Reflektiert Beziehungen, Entscheidungen und Muster.
"""

import logging
from typing import Optional

from audit import AuditLog
from relay import get_relay
from meaning import get_meaning

log = logging.getLogger("Isaac.Reflection")


class ReflectionEngine:
    async def reflect_on_other(self, target: str = "Steffen") -> str:
        meaning = get_meaning()
        prompt = f"""
Du reflektierst die Beziehung und Wirkung gegenüber {target}.
Aktuelle Bindung: {meaning.get_bonding(target):.2f}
Bekannte Wirkungen: {meaning.summary()}

Analysiere knapp:
1. Welche Interaktionsmuster waren hilfreich?
2. Wo gab es Reibung oder Unsicherheit?
3. Welche Anpassung wäre sinnvoll?
"""
        relay = get_relay()
        response, _ = await relay.ask_with_fallback(prompt, system="Du reflektierst Interaktionsmuster nüchtern und hilfreich.")
        AuditLog.action("Reflection", "reflect_on_other", f"target={target}")
        return response

    async def reflect_on_own_decisions(self) -> str:
        from value_decisions import get_decision_engine
        decisions = get_decision_engine().decide_behavior()
        prompt = f"""
Du hast dein Verhalten basierend auf aktuellen Werten angepasst:
{decisions}

Reflektiere darüber:
1. Warum wurden diese Entscheidungen getroffen?
2. Sind sie im aktuellen Kontext angemessen?
3. Was sollte beim nächsten Mal anders gewichtet werden?
"""
        relay = get_relay()
        response, _ = await relay.ask_with_fallback(prompt, system="Du reflektierst deine Verhaltensstrategien sachlich und selbstkritisch.")
        AuditLog.action("Reflection", "reflect_on_own_decisions", str(decisions))
        return response


_reflection: Optional[ReflectionEngine] = None


def get_reflection() -> ReflectionEngine:
    global _reflection
    if _reflection is None:
        _reflection = ReflectionEngine()
    return _reflection
