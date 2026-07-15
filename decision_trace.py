from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TracePhase(Enum):
    GOVERNANCE = "governance"
    CLASSIFICATION = "classification"
    RETRIEVAL = "retrieval"
    STRATEGY = "strategy"
    MOTIVATION = "motivation"
    ELIGIBILITY = "eligibility"
    SELECTION = "selection"
    EXECUTION = "execution"
    CONTEXT_INTEGRATION = "context_integration"
    EVALUATION = "evaluation"
    LEARNING = "learning"
    FOLLOWUP = "followup"


@dataclass(frozen=True)
class TraceEntry:
    sequence: int
    ts: float
    phase: TracePhase
    event: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "ts": self.ts,
            "phase": self.phase.value,
            "event": self.event,
            "data": self.data,
        }


@dataclass
class DecisionTrace:
    entries: list[TraceEntry] = field(default_factory=list)

    def add(self, phase: TracePhase, event: str, data: dict[str, Any] | None = None) -> TraceEntry:
        payload = dict(data or {})
        entry = TraceEntry(
            sequence=len(self.entries) + 1,
            ts=time.time(),
            phase=phase,
            event=event,
            data=payload,
        )
        self.entries.append(entry)
        return entry

    def to_list(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.entries]


def gate_trace_data(gate: dict[str, Any] | None) -> dict[str, Any]:
    """Serialisiert ein Verfassungs-Gate-Urteil für DecisionTrace/Audit."""
    payload = dict(gate or {})
    override = payload.get("override") or {}
    verdict = payload.get("verdict") or {}
    blocked_by = list(payload.get("blocked_by") or verdict.get("blocked_by") or [])
    return {
        "allowed": bool(payload.get("allowed")),
        "overridden": bool(override.get("overridden")),
        "blocked_by": blocked_by,
        "action": str(verdict.get("action") or payload.get("action") or ""),
    }


def audit_routing_trace(
    trace: DecisionTrace,
    *,
    intent: str = "",
    outcome: str = "",
) -> None:
    """Persistiert einen Routing-DecisionTrace im append-only Audit-Log."""
    from audit import AuditLog

    AuditLog._record(
        "decision_trace",
        {
            "scope": "routing",
            "intent": (intent or "")[:80],
            "outcome": (outcome or "")[:40],
            "entries": trace.to_list(),
        },
    )
