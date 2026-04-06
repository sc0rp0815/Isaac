from __future__ import annotations

"""Isaac – Learning Policy
Gewichtete Lernupdates mit Bremse für Hochrisiko-Veränderungen.
"""

from dataclasses import dataclass


@dataclass
class EvidenceScore:
    direction: float = 0.0
    evidence_strength: float = 0.5
    repetition: float = 1.0
    consistency: float = 1.0
    relevance: float = 1.0
    safety_factor: float = 1.0

    def delta(self) -> float:
        return (
            self.direction
            * self.evidence_strength
            * self.repetition
            * self.consistency
            * self.relevance
            * self.safety_factor
        )


RISK_SAFETY = {
    "preference": 1.0,
    "relationship": 0.7,
    "procedure": 0.6,
    "value": 0.25,
    "identity": 0.1,
}


def bounded_update(kind: str, direction: float, evidence_strength: float = 0.5,
                   repetition: float = 1.0, consistency: float = 1.0,
                   relevance: float = 1.0) -> float:
    safety = RISK_SAFETY.get(kind, 0.3)
    score = EvidenceScore(
        direction=direction,
        evidence_strength=max(0.0, min(1.0, evidence_strength)),
        repetition=max(0.0, min(2.0, repetition)),
        consistency=max(0.0, min(1.0, consistency)),
        relevance=max(0.0, min(1.0, relevance)),
        safety_factor=safety,
    )
    return score.delta()
