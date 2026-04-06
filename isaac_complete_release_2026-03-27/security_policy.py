from __future__ import annotations

"""Isaac – Security Policy & Confirmation Queue
Zusätzliche Schutzschicht über Privilege/Constitution:
- analysiert riskante Aktionen
- erstellt Review-Einträge für bestätigungspflichtige Aktionen
- hält Queue persistent in JSON
"""

import json
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR, Level
from audit import AuditLog

QUEUE_PATH = DATA_DIR / "confirmation_queue.json"


@dataclass
class SecurityVerdict:
    allowed: bool
    reason: str
    requires_confirmation: bool = False
    risk: str = 'low'
    queue_id: str = ''


class ConfirmationPolicy:
    def __init__(self, path: Path = QUEUE_PATH):
        self.path = path
        self._queue: list[dict[str, Any]] = self._load()

    def _load(self) -> list[dict[str, Any]]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding='utf-8'))
            except Exception:
                return []
        return []

    def _save(self):
        self.path.write_text(json.dumps(self._queue, ensure_ascii=False, indent=2), encoding='utf-8')

    def pending(self) -> list[dict[str, Any]]:
        return [q for q in self._queue if q.get('status') == 'pending']

    def all(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(reversed(self._queue[-limit:]))

    def _enqueue(self, aktion: str, ctx, metadata: dict[str, Any], reason: str) -> str:
        qid = 'REV-' + uuid.uuid4().hex[:10]
        entry = {
            'id': qid,
            'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'pending',
            'aktion': aktion,
            'caller': getattr(ctx, 'caller', 'unknown'),
            'level': int(getattr(ctx, 'level', 0)),
            'r_trace': getattr(ctx, 'r_trace', ''),
            'metadata': metadata,
            'reason': reason,
            'decision_ts': '',
            'decision_by': '',
            'decision_note': '',
        }
        self._queue.append(entry)
        self._save()
        AuditLog.confirmation('queued', aktion, qid, reason)
        return qid

    def decide(self, queue_id: str, approved: bool, decided_by: str = 'owner', note: str = '') -> Optional[dict[str, Any]]:
        for q in self._queue:
            if q.get('id') == queue_id:
                q['status'] = 'approved' if approved else 'rejected'
                q['decision_ts'] = time.strftime('%Y-%m-%d %H:%M:%S')
                q['decision_by'] = decided_by
                q['decision_note'] = note[:300]
                self._save()
                AuditLog.confirmation(q['status'], q.get('aktion', ''), queue_id, note)
                return q
        return None

    def approved_for(self, aktion: str, ctx) -> bool:
        caller = getattr(ctx, 'caller', '')
        trace = getattr(ctx, 'r_trace', '')
        for q in reversed(self._queue):
            if q.get('status') != 'approved':
                continue
            if q.get('aktion') == aktion and q.get('caller') == caller and q.get('r_trace') == trace:
                return True
        return False

    def analyze(self, aktion: str, ctx, metadata: dict[str, Any]) -> SecurityVerdict:
        risk = (metadata.get('risk') or 'medium').lower()
        outside = bool(metadata.get('outside_effect', False))
        caller_level = int(getattr(ctx, 'level', 0))
        # Owner-level skips confirmations.
        if caller_level >= Level.STEFFEN:
            return SecurityVerdict(True, 'Owner-level approved', False, risk)
        # previously approved identical review
        if self.approved_for(aktion, ctx):
            return SecurityVerdict(True, 'Previously approved by owner', False, risk)

        requires = False
        reason = ''
        if metadata.get('privilege_escalation'):
            requires = True
            reason = 'Rechteausweitung ist bestätigungspflichtig'
        elif risk == 'critical':
            requires = True
            reason = 'Kritische Aktion ist bestätigungspflichtig'
        elif risk == 'high' and outside:
            requires = True
            reason = 'Hochriskante Aktion mit Außenwirkung ist bestätigungspflichtig'
        elif aktion in {'execute_code', 'system_command', 'file_delete', 'wipe_memory'}:
            requires = True
            reason = 'Aktion fällt unter Confirmation Policy'

        if not requires:
            return SecurityVerdict(True, 'No additional confirmation required', False, risk)
        qid = self._enqueue(aktion, ctx, metadata, reason)
        return SecurityVerdict(False, f'{reason} | Review-ID: {qid}', True, risk, qid)


_policy: Optional[ConfirmationPolicy] = None


def get_confirmation_policy() -> ConfirmationPolicy:
    global _policy
    if _policy is None:
        _policy = ConfirmationPolicy()
    return _policy
