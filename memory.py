"""
Isaac – Gedächtnis (SQLite)
============================
Persistentes, durchsuchbares Gedächtnis auf drei Ebenen:

  1. Working Memory    – letzte N Konversationen (RAM + DB)
  2. Faktenspeicher    – Steffen-Wissen, Korrekturen, Kontext
  3. Direktiven-Store  – Steffen-Direktiven (permanent)

SQLite ist atomar: kein Datenverlust bei Absturz.
FTS5 für Volltextsuche.
"""

import sqlite3
import json
import time
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Any
from contextlib import contextmanager

from config import DB_PATH, get_config
from audit  import AuditLog

log = logging.getLogger("Isaac.Memory")

MIN_RETRIEVAL_CONFIDENCE = 0.12
PREFERENCE_KEY_MARKERS = ("pref", "stil", "antwort", "tool", "chat", "agreement")
OWNER_SOURCES = frozenset({"steffen", "owner"})


@dataclass(frozen=True)
class RetrievalContext:
    query: str
    active_directives: list[dict]
    relevant_facts: list[dict]
    semantic_context: str
    conversation_history: list[dict]
    relevant_task_results: list[dict]
    preferences_context: list[dict]
    project_context: list[dict]
    behavioral_risks: list[dict]
    relevant_reflections: list[str]
    open_questions: list[str]
    relevant_procedures: list[dict]

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "active_directives": self.active_directives,
            "relevant_facts": self.relevant_facts,
            "semantic_context": self.semantic_context,
            "conversation_history": self.conversation_history,
            "relevant_task_results": self.relevant_task_results,
            "preferences_context": self.preferences_context,
            "project_context": self.project_context,
            "behavioral_risks": self.behavioral_risks,
            "relevant_reflections": self.relevant_reflections,
            "open_questions": self.open_questions,
            "relevant_procedures": self.relevant_procedures,
        }


# ── Schema ─────────────────────────────────────────────────────────────────────
SCHEMA = """
-- Konversations-Verlauf
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    role        TEXT    NOT NULL,   -- 'steffen' | 'isaac' | 'instance'
    text        TEXT    NOT NULL,
    task_id     TEXT    DEFAULT '',
    provider    TEXT    DEFAULT '',
    quality     REAL    DEFAULT 0.0,
    metadata    TEXT    DEFAULT '{}'
);

-- Fakten (Langzeit-Wissen)
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    key         TEXT    NOT NULL UNIQUE,
    value       TEXT    NOT NULL,
    source      TEXT    DEFAULT '',
    confidence  REAL    DEFAULT 1.0,
    updated     TEXT    NOT NULL
);

-- Steffen-Direktiven
CREATE TABLE IF NOT EXISTS directives (
    id          TEXT    PRIMARY KEY,
    ts          TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    priority    INTEGER DEFAULT 10,
    active      INTEGER DEFAULT 1
);

-- Task-Ergebnisse (komprimiert, für Referenz)
CREATE TABLE IF NOT EXISTS task_results (
    id          TEXT    PRIMARY KEY,
    ts          TEXT    NOT NULL,
    description TEXT    NOT NULL,
    result      TEXT    NOT NULL,
    score       REAL    DEFAULT 0.0,
    iterations  INTEGER DEFAULT 1,
    provider    TEXT    DEFAULT '',
    tags        TEXT    DEFAULT '[]'
);

-- Entwicklungslog (Lern- und Wertänderungen)
CREATE TABLE IF NOT EXISTS development_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                  TEXT    NOT NULL,
    event_type          TEXT    NOT NULL,
    target_kind         TEXT    NOT NULL,
    target_key          TEXT    NOT NULL,
    delta               REAL    DEFAULT 0.0,
    confidence_before   REAL    DEFAULT 0.0,
    confidence_after    REAL    DEFAULT 0.0,
    evidence_refs       TEXT    DEFAULT '[]',
    contradiction_refs  TEXT    DEFAULT '[]',
    reason              TEXT    DEFAULT '',
    requires_review     INTEGER DEFAULT 0,
    reviewed_by_owner   INTEGER DEFAULT 0,
    metadata            TEXT    DEFAULT '{}'
);

-- Wiederverwendbare Task-Verfahren (Skill-/Procedure-Memory)
CREATE TABLE IF NOT EXISTS task_procedures (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    signature           TEXT    NOT NULL UNIQUE,
    ts                  TEXT    NOT NULL,
    task_type           TEXT    NOT NULL,
    intent_hint         TEXT    DEFAULT '',
    keywords            TEXT    DEFAULT '[]',
    tools_used          TEXT    DEFAULT '[]',
    trace_summary       TEXT    DEFAULT '',
    reliability         REAL    DEFAULT 0.5,
    success_count       INTEGER DEFAULT 0,
    failure_count       INTEGER DEFAULT 0,
    last_task_id        TEXT    DEFAULT '',
    last_score          REAL    DEFAULT 0.0,
    last_status         TEXT    DEFAULT '',
    degraded            INTEGER DEFAULT 0,
    metadata            TEXT    DEFAULT '{}'
);

-- Archivierte Entwicklungs-Events (Forgetting/Decay)
CREATE TABLE IF NOT EXISTS development_events_archive (
    id                  INTEGER PRIMARY KEY,
    ts                  TEXT    NOT NULL,
    event_type          TEXT    NOT NULL,
    target_kind         TEXT    NOT NULL,
    target_key          TEXT    NOT NULL,
    delta               REAL    DEFAULT 0.0,
    confidence_before   REAL    DEFAULT 0.0,
    confidence_after    REAL    DEFAULT 0.0,
    evidence_refs       TEXT    DEFAULT '[]',
    contradiction_refs  TEXT    DEFAULT '[]',
    reason              TEXT    DEFAULT '',
    requires_review     INTEGER DEFAULT 0,
    reviewed_by_owner   INTEGER DEFAULT 0,
    metadata            TEXT    DEFAULT '{}',
    archived_at         TEXT    NOT NULL
);

-- Task-Checkpoints für Resume
CREATE TABLE IF NOT EXISTS task_checkpoints (
    checkpoint_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id             TEXT    NOT NULL,
    ts                  TEXT    NOT NULL,
    state_name          TEXT    NOT NULL,
    input_snapshot      TEXT    DEFAULT '{}',
    tool_snapshot       TEXT    DEFAULT '{}',
    result_snapshot     TEXT    DEFAULT '{}',
    memory_refs         TEXT    DEFAULT '[]',
    side_effect_refs    TEXT    DEFAULT '[]'
);

-- FTS für Konversationen
CREATE VIRTUAL TABLE IF NOT EXISTS conv_fts USING fts5(
    text, content='conversations', content_rowid='id'
);

-- FTS für Fakten
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    key, value, content='facts', content_rowid='id'
);

-- Trigger für FTS-Sync
CREATE TRIGGER IF NOT EXISTS conv_ai AFTER INSERT ON conversations BEGIN
    INSERT INTO conv_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, key, value) VALUES (new.id, new.key, new.value);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, key, value)
        VALUES('delete', old.id, old.key, old.value);
    INSERT INTO facts_fts(rowid, key, value) VALUES (new.id, new.key, new.value);
END;
"""

# ── Verbindung ────────────────────────────────────────────────────────────────
@contextmanager
def _conn():
    """Thread-safe SQLite-Verbindung mit WAL-Mode."""
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False,
                          timeout=10.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with _conn() as con:
        con.executescript(SCHEMA)
    log.info(f"DB initialisiert: {DB_PATH}")


# ── Memory-Klasse ──────────────────────────────────────────────────────────────
class Memory:
    """
    Isaacs Gedächtnis.
    Alle Schreib-Operationen erzeugen Audit-Einträge.
    """

    def __init__(self):
        init_db()
        self._working: list[dict] = []
        self._load_working_memory()
        # Vektor-Gedächtnis (semantisch, optional)
        from vector_memory import get_vector_memory
        self._vector = get_vector_memory()
        log.info(
            f"Memory online │ Working: {len(self._working)} Einträge │ "
            f"Vector: {'aktiv' if self._vector.aktiv else 'inaktiv (pip install chromadb)'}"
        )

    # ── Konversation ──────────────────────────────────────────────────────────
    def add_conversation(self, role: str, text: str,
                         task_id: str = "", provider: str = "",
                         quality: float = 0.0, metadata: dict = None,
                         stimmung: str = "neutral"):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        meta = json.dumps(metadata or {})
        with _conn() as con:
            cur = con.execute(
                "INSERT INTO conversations (ts, role, text, task_id, "
                "provider, quality, metadata) VALUES (?,?,?,?,?,?,?)",
                (ts, role, text, task_id, provider, quality, meta)
            )
            conv_id = str(cur.lastrowid)
        entry = {"ts": ts, "role": role, "text": text,
                 "task_id": task_id, "provider": provider,
                 "quality": quality}
        self._working.append(entry)
        cfg = get_config()
        if len(self._working) > cfg.memory.max_working_memory:
            self._working = self._working[-cfg.memory.max_working_memory:]
        AuditLog.memory_write("Memory", "conversation", role)
        # Semantisch speichern
        self._vector.speichere_konversation(
            conv_id   = conv_id,
            text      = text,
            role      = role,
            ts        = ts,
            stimmung  = stimmung,
            qualitaet = quality,
        )

    def get_working_memory(self, n: int = 10) -> list[dict]:
        """Gibt die letzten n Konversations-Einträge zurück."""
        return self._working[-n:]

    def search_conversations(self, query: str, limit: int = 10) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                """SELECT c.* FROM conversations c
                   JOIN conv_fts ON conv_fts.rowid = c.id
                   WHERE conv_fts MATCH ?
                   ORDER BY c.id DESC LIMIT ?""",
                (query, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Fakten ────────────────────────────────────────────────────────────────
    @staticmethod
    def _is_preference_key(key: str) -> bool:
        lowered = (key or "").lower()
        return any(marker in lowered for marker in PREFERENCE_KEY_MARKERS)

    @staticmethod
    def _is_owner_source(source: str) -> bool:
        return (source or "").strip().lower() in OWNER_SOURCES

    def get_fact_record(self, key: str) -> Optional[dict]:
        with _conn() as con:
            row = con.execute("SELECT * FROM facts WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def update_fact_confidence(self, key: str, confidence: float) -> bool:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with _conn() as con:
            cur = con.execute(
                "UPDATE facts SET confidence=?, updated=? WHERE key=?",
                (float(confidence), ts, key),
            )
        return cur.rowcount > 0

    def set_fact(self, key: str, value: str, source: str = "",
                 confidence: float = 1.0) -> bool:
        """Schreibt oder aktualisiert eine Tatsache."""
        from learning_policy import bounded_update

        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        owner_confirmed = self._is_owner_source(source)
        if owner_confirmed:
            confidence = 1.0

        with _conn() as con:
            existing = con.execute(
                "SELECT id, value, confidence, source FROM facts WHERE key=?", (key,)
            ).fetchone()
            if existing:
                old_value = (existing["value"] or "").strip()
                old_conf = float(existing["confidence"] or 1.0)
                new_conf = float(confidence)
                if (
                    old_value
                    and old_value != value.strip()
                    and not owner_confirmed
                ):
                    delta = bounded_update(
                        "preference",
                        -1.0,
                        evidence_strength=0.8,
                        repetition=1.0,
                    )
                    new_conf = max(MIN_RETRIEVAL_CONFIDENCE, min(new_conf, old_conf + delta))
                    try:
                        self.log_development_event(
                            event_type="fact_contradiction",
                            target_kind="fact",
                            target_key=key,
                            delta=round(new_conf - old_conf, 4),
                            confidence_before=old_conf,
                            confidence_after=new_conf,
                            contradiction_refs=[old_value[:120]],
                            reason=f"Widerspruch: '{old_value[:80]}' → '{value[:80]}'",
                            requires_review=True,
                            metadata={"source": source, "old_value": old_value[:120]},
                        )
                    except Exception as e:
                        log.debug(f"Contradiction-Log: {e}")
                con.execute(
                    "UPDATE facts SET value=?, source=?, "
                    "confidence=?, updated=? WHERE key=?",
                    (value, source, new_conf, ts, key)
                )
            else:
                if self._is_preference_key(key) and not owner_confirmed:
                    confidence = min(float(confidence), 0.65)
                con.execute(
                    "INSERT INTO facts (ts, key, value, source, "
                    "confidence, updated) VALUES (?,?,?,?,?,?)",
                    (ts, key, value, source, confidence, ts)
                )
        AuditLog.memory_write("Memory", "fact", key)
        return True

    def get_fact(self, key: str) -> Optional[str]:
        with _conn() as con:
            row = con.execute(
                "SELECT value FROM facts WHERE key=?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def list_decay_candidate_facts(self, limit: int = 100) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM facts ORDER BY updated ASC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        candidates = []
        for row in rows:
            fact = dict(row)
            key = fact.get("key", "")
            conf = float(fact.get("confidence") or 0.0)
            if not self._is_preference_key(key):
                continue
            if conf > 0.75:
                continue
            if self._is_owner_source(fact.get("source", "")) and conf >= 0.9:
                continue
            candidates.append(fact)
        return candidates

    def search_facts(self, query: str, limit: int = 10) -> list[dict]:
        terms = [t for t in re.findall(r"[\w]+", (query or "").lower()) if len(t) >= 2]
        if not terms:
            return []
        fts_query = " OR ".join(terms[:8])
        with _conn() as con:
            try:
                rows = con.execute(
                    """SELECT f.* FROM facts f
                       JOIN facts_fts ON facts_fts.rowid = f.id
                       WHERE facts_fts MATCH ?
                       ORDER BY f.confidence DESC LIMIT ?""",
                    (fts_query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                like = f"%{' '.join(terms[:3])}%"
                rows = con.execute(
                    """SELECT * FROM facts
                       WHERE key LIKE ? OR value LIKE ?
                       ORDER BY confidence DESC LIMIT ?""",
                    (like, like, limit),
                ).fetchall()
        return [
            dict(r) for r in rows
            if float(r["confidence"] or 0.0) >= MIN_RETRIEVAL_CONFIDENCE
        ]

    def all_facts(self) -> dict[str, str]:
        with _conn() as con:
            rows = con.execute(
                "SELECT key, value FROM facts ORDER BY updated DESC LIMIT 200"
            ).fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ── Direktiven ────────────────────────────────────────────────────────────
    def save_directive(self, directive_id: str, text: str,
                       priority: int = 10):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with _conn() as con:
            con.execute(
                "INSERT OR REPLACE INTO directives "
                "(id, ts, text, priority, active) VALUES (?,?,?,?,1)",
                (directive_id, ts, text, priority)
            )

    def revoke_directive(self, directive_id: str):
        with _conn() as con:
            con.execute(
                "UPDATE directives SET active=0 WHERE id=?",
                (directive_id,)
            )

    def get_directives(self) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM directives WHERE active=1 "
                "ORDER BY priority DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Task-Ergebnisse ───────────────────────────────────────────────────────
    def save_task_result(self, task_id: str, description: str,
                         result: str, score: float = 0.0,
                         iterations: int = 1, provider: str = "",
                         tags: list = None):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with _conn() as con:
            con.execute(
                "INSERT OR REPLACE INTO task_results "
                "(id, ts, description, result, score, iterations, "
                "provider, tags) VALUES (?,?,?,?,?,?,?,?)",
                (task_id, ts, description, result[:2000],
                 score, iterations, provider,
                 json.dumps(tags or []))
            )

    def get_relevant_results(self, query: str, limit: int = 3) -> list[dict]:
        """Findet frühere Task-Ergebnisse die zu einer Anfrage passen."""
        with _conn() as con:
            rows = con.execute(
                """SELECT * FROM task_results
                   WHERE description LIKE ? OR result LIKE ?
                   ORDER BY score DESC LIMIT ?""",
                (f"%{query[:30]}%", f"%{query[:30]}%", limit)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Task-Verfahren (Procedure Memory) ─────────────────────────────────────
    def get_procedure_by_signature(self, signature: str) -> Optional[dict]:
        with _conn() as con:
            row = con.execute(
                "SELECT * FROM task_procedures WHERE signature=?", (signature,)
            ).fetchone()
        return dict(row) if row else None

    def upsert_procedure(
        self,
        signature: str,
        task_type: str,
        intent_hint: str = "",
        keywords: list | None = None,
        tools_used: list | None = None,
        trace_summary: str = "",
        reliability: float = 0.5,
        success_count: int = 0,
        failure_count: int = 0,
        last_task_id: str = "",
        last_score: float = 0.0,
        last_status: str = "",
        degraded: bool = False,
        metadata: dict | None = None,
    ) -> int:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with _conn() as con:
            existing = con.execute(
                "SELECT id FROM task_procedures WHERE signature=?", (signature,)
            ).fetchone()
            values = (
                ts,
                task_type,
                intent_hint[:120],
                json.dumps(keywords or [], ensure_ascii=False),
                json.dumps(tools_used or [], ensure_ascii=False),
                trace_summary[:300],
                float(reliability),
                int(success_count),
                int(failure_count),
                last_task_id,
                float(last_score),
                last_status,
                1 if degraded else 0,
                json.dumps(metadata or {}, ensure_ascii=False),
            )
            if existing:
                con.execute(
                    "UPDATE task_procedures SET ts=?, task_type=?, intent_hint=?, "
                    "keywords=?, tools_used=?, trace_summary=?, reliability=?, "
                    "success_count=?, failure_count=?, last_task_id=?, last_score=?, "
                    "last_status=?, degraded=?, metadata=? WHERE signature=?",
                    (*values, signature),
                )
                proc_id = int(existing["id"])
            else:
                cur = con.execute(
                    "INSERT INTO task_procedures "
                    "(signature, ts, task_type, intent_hint, keywords, tools_used, "
                    "trace_summary, reliability, success_count, failure_count, "
                    "last_task_id, last_score, last_status, degraded, metadata) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (signature, *values),
                )
                proc_id = int(cur.lastrowid)
        AuditLog.memory_write("Memory", "procedure", signature[:12])
        return proc_id

    def _normalize_procedure(self, proc: dict) -> dict:
        return {
            "signature": proc.get("signature", ""),
            "task_type": proc.get("task_type", ""),
            "intent_hint": (proc.get("intent_hint") or "")[:120],
            "keywords": json.loads(proc.get("keywords") or "[]"),
            "tools_used": json.loads(proc.get("tools_used") or "[]"),
            "trace_summary": (proc.get("trace_summary") or "")[:200],
            "reliability": float(proc.get("reliability") or 0.0),
            "success_count": int(proc.get("success_count") or 0),
            "failure_count": int(proc.get("failure_count") or 0),
            "degraded": bool(proc.get("degraded")),
            "last_status": proc.get("last_status", ""),
            "last_score": float(proc.get("last_score") or 0.0),
        }

    def search_procedures(self, query: str, limit: int = 3) -> list[dict]:
        terms = [t for t in re.findall(r"\w+", (query or "").lower()) if len(t) >= 3]
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM task_procedures "
                "ORDER BY reliability DESC, ts DESC LIMIT 80"
            ).fetchall()
        scored: list[tuple[float, dict]] = []
        for row in rows:
            proc = dict(row)
            keywords = json.loads(proc.get("keywords") or "[]")
            hint = (proc.get("intent_hint") or "").lower()
            overlap = 0.0
            for term in terms:
                if any(term in kw or kw in term for kw in keywords):
                    overlap += 1.0
                elif term in hint:
                    overlap += 0.5
            if not terms:
                overlap = 0.5
            reliability = float(proc.get("reliability") or 0.0)
            rank = overlap * reliability
            if proc.get("degraded"):
                rank *= 0.35
            if overlap > 0 or not terms:
                scored.append((rank, proc))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            self._normalize_procedure(proc)
            for rank, proc in scored[: max(1, int(limit))]
            if rank > 0 or not terms
        ]

    def list_procedures(self, limit: int = 20) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM task_procedures "
                "ORDER BY reliability DESC, ts DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [self._normalize_procedure(dict(r)) for r in rows]

    def build_retrieval_context(
        self, user_input: str, intent: str = "", interaction_class: str = "",
        n_history: int = 6
    ) -> RetrievalContext:
        query_terms = [w for w in re.findall(r"\w+", user_input.lower()) if len(w) >= 4][:5]
        query = " ".join(query_terms) or user_input[:40]
        directives = self.get_directives()[:3]
        facts = [
            f for f in (self.search_facts(query, limit=8) if query else [])
            if float(f.get("confidence") or 0.0) >= MIN_RETRIEVAL_CONFIDENCE
        ]
        seen_fact_keys = {f.get("key") for f in facts}
        for term in {w for w in re.findall(r"\w+", user_input.lower()) if len(w) >= 3}:
            def_key = f"definition.{term}"
            if def_key in seen_fact_keys:
                continue
            record = self.get_fact_record(def_key)
            if (
                record
                and float(record.get("confidence") or 0.0) >= MIN_RETRIEVAL_CONFIDENCE
            ):
                facts.append(record)
                seen_fact_keys.add(def_key)
        facts = facts[:6]
        relevant_results = self.get_relevant_results(query, limit=4) if query else []
        relevant_procedures = self.search_procedures(query, limit=3) if query else []
        history = self.get_working_memory(n_history)
        vector = getattr(self, "_vector", None)
        semantic_context = ""
        if query and vector and vector.aktiv:
            semantic_context = vector.als_kontext(query) or ""

        active_directives = []
        preferences = []
        for directive in directives:
            text = (directive.get("text") or "").strip()
            if not text:
                continue
            active_directives.append({
                "id": directive.get("id", ""),
                "text": text[:180],
                "priority": directive.get("priority", 0),
            })
            preferences.append({
                "source": "directive",
                "text": text[:180],
                "priority": directive.get("priority", 0),
            })

        relevant_facts = []
        for fact in facts:
            value = (fact.get("value") or "").strip()
            normalized = {
                "key": fact.get("key", ""),
                "value": value[:180],
                "confidence": fact.get("confidence", 0.0),
                "source": fact.get("source", ""),
            }
            relevant_facts.append(normalized)
            key = (fact.get("key") or "").lower()
            if (
                self._is_preference_key(key)
                and normalized["confidence"] >= MIN_RETRIEVAL_CONFIDENCE
            ):
                preferences.append({
                    "source": "fact",
                    "key": normalized["key"],
                    "value": normalized["value"],
                    "confidence": normalized["confidence"],
                })

        conversation_history = []
        project_context = []
        for entry in history:
            text = (entry.get("text") or "").strip()
            normalized = {
                "role": entry.get("role", ""),
                "text": text[:180],
            }
            conversation_history.append(normalized)
            if any(marker in text.lower() for marker in ("isaac", "routing", "executor", "tool", "klass", "class")):
                project_context.append(normalized)
        project_context = project_context[-3:]

        relevant_task_results = []
        behavioral_risks = []
        relevant_reflections = []
        for result in relevant_results:
            normalized = {
                "description": (result.get("description") or "")[:120],
                "result": (result.get("result") or "")[:220],
                "score": result.get("score", 0.0),
                "provider": result.get("provider", ""),
            }
            relevant_task_results.append(normalized)
            result_text = normalized["result"].lower()
            risk_tags = []
            if "tools genutzt" in result_text or "tool" in result_text:
                risk_tags.append("tool_overreach_risk")
            if normalized["score"] <= 4.0:
                risk_tags.append("quality_regression_risk")
            if risk_tags:
                behavioral_risks.append({
                    "description": normalized["description"],
                    "score": normalized["score"],
                    "risks": risk_tags,
                })
            if "reflekt" in result_text or "pattern" in result_text:
                relevant_reflections.append(normalized["result"])

        open_questions = []
        if intent == "chat" and interaction_class == "NORMAL_CHAT" and len(user_input.split()) <= 2 and "?" not in user_input:
            open_questions.append("Nutzerabsicht bei sehr kurzem Input potenziell unklar.")

        for proc in relevant_procedures:
            if proc.get("degraded"):
                behavioral_risks.append({
                    "description": proc.get("intent_hint") or proc.get("task_type", "procedure"),
                    "score": proc.get("reliability", 0.0),
                    "risks": ["degraded_procedure"],
                })

        return RetrievalContext(
            query=query,
            active_directives=active_directives,
            relevant_facts=relevant_facts[:6],
            semantic_context=semantic_context.strip(),
            conversation_history=conversation_history[-n_history:],
            relevant_task_results=relevant_task_results[:4],
            preferences_context=preferences[:4],
            project_context=project_context,
            behavioral_risks=behavioral_risks[:3],
            relevant_reflections=relevant_reflections[:2],
            open_questions=open_questions[:1],
            relevant_procedures=relevant_procedures[:3],
        )

    def format_retrieval_context(self, retrieval_ctx: RetrievalContext | dict[str, Any]) -> str:
        if isinstance(retrieval_ctx, RetrievalContext):
            data = retrieval_ctx.as_dict()
        else:
            data = retrieval_ctx or {}

        sections: list[str] = []
        if data.get("active_directives"):
            sections.append("[active_directives]")
            for directive in data["active_directives"]:
                sections.append(
                    f"  - prio={directive.get('priority', 0)}: {directive.get('text', '')}"
                )
        if data.get("relevant_facts"):
            sections.append("[relevant_facts]")
            for fact in data["relevant_facts"]:
                sections.append(f"  - {fact.get('key', '')}: {fact.get('value', '')}")
        if data.get("semantic_context"):
            sections.append("[semantic_context]")
            sections.append(data["semantic_context"])
        if data.get("conversation_history"):
            sections.append("[conversation_history]")
            for entry in data["conversation_history"]:
                sections.append(f"  - {entry.get('role', '')}: {entry.get('text', '')}")
        if data.get("relevant_task_results"):
            sections.append("[relevant_task_results]")
            for result in data["relevant_task_results"]:
                sections.append(
                    f"  - score={result.get('score', 0.0)} {result.get('description', '')}: {result.get('result', '')}"
                )
        if data.get("preferences_context"):
            sections.append("[preferences_context]")
            for item in data["preferences_context"]:
                if item.get("source") == "directive":
                    sections.append(
                        f"  - directive(prio={item.get('priority', 0)}): {item.get('text', '')}"
                    )
                else:
                    sections.append(f"  - fact {item.get('key', '')}: {item.get('value', '')}")
        if data.get("project_context"):
            sections.append("[project_context]")
            for item in data["project_context"]:
                sections.append(f"  - {item.get('role', '')}: {item.get('text', '')}")
        if data.get("behavioral_risks"):
            sections.append("[behavioral_risks]")
            for risk in data["behavioral_risks"]:
                sections.append(f"  - {','.join(risk.get('risks', []))}: {risk.get('description', '')}")
        if data.get("relevant_reflections"):
            sections.append("[relevant_reflections]")
            for ref in data["relevant_reflections"]:
                sections.append(f"  - {ref}")
        if data.get("open_questions"):
            sections.append("[open_questions]")
            for q in data["open_questions"]:
                sections.append(f"  - {q}")
        if data.get("relevant_procedures"):
            sections.append("[relevant_procedures]")
            for proc in data["relevant_procedures"]:
                tools = ", ".join(proc.get("tools_used") or []) or "keine"
                flag = " DEGRADED" if proc.get("degraded") else ""
                sections.append(
                    f"  - rel={proc.get('reliability', 0.0):.2f}{flag} "
                    f"{proc.get('task_type', '')} tools={tools}: "
                    f"{proc.get('trace_summary') or proc.get('intent_hint', '')}"
                )
        return "\n".join(sections).strip()

    # ── Kontext-Aufbau für Relay ───────────────────────────────────────────────
    def build_context(self, query: str = "", n_history: int = 6) -> str:
        """Legacy-Wrapper: nutzt den strukturierten Retrieval-Kontext."""
        retrieval_ctx = self.build_retrieval_context(query, n_history=n_history)
        return self.format_retrieval_context(retrieval_ctx)

    # ── Statistiken ───────────────────────────────────────────────────────────
    def stats(self) -> dict:
        with _conn() as con:
            n_conv  = con.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            n_facts = con.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            n_tasks = con.execute("SELECT COUNT(*) FROM task_results").fetchone()[0]
            n_proc  = con.execute("SELECT COUNT(*) FROM task_procedures").fetchone()[0]
            n_dir   = con.execute(
                "SELECT COUNT(*) FROM directives WHERE active=1"
            ).fetchone()[0]
        return {
            "conversations":  n_conv,
            "facts":          n_facts,
            "task_results":   n_tasks,
            "procedures":     n_proc,
            "directives":     n_dir,
            "working_memory": len(self._working),
            "vector":         self._vector.stats(),
        }

    def _load_working_memory(self):
        cfg = get_config()
        n = cfg.memory.max_working_memory
        with _conn() as con:
            rows = con.execute(
                "SELECT ts, role, text, task_id, provider, quality "
                "FROM conversations ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
        self._working = [dict(r) for r in reversed(rows)]

    # ── Entwicklungslog ───────────────────────────────────────────────────────
    def log_development_event(
        self,
        event_type: str,
        target_kind: str,
        target_key: str,
        delta: float = 0.0,
        confidence_before: float = 0.0,
        confidence_after: float = 0.0,
        evidence_refs: list | None = None,
        contradiction_refs: list | None = None,
        reason: str = "",
        requires_review: bool = False,
        metadata: dict | None = None,
    ) -> int:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with _conn() as con:
            cur = con.execute(
                "INSERT INTO development_events "
                "(ts, event_type, target_kind, target_key, delta, confidence_before, "
                "confidence_after, evidence_refs, contradiction_refs, reason, "
                "requires_review, reviewed_by_owner, metadata) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ts,
                    event_type,
                    target_kind,
                    target_key,
                    float(delta),
                    float(confidence_before),
                    float(confidence_after),
                    json.dumps(evidence_refs or [], ensure_ascii=False),
                    json.dumps(contradiction_refs or [], ensure_ascii=False),
                    reason[:300],
                    1 if requires_review else 0,
                    0,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            return int(cur.lastrowid)

    def recent_development_events(self, n: int = 20) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM development_events ORDER BY id DESC LIMIT ?",
                (max(1, int(n)),),
            ).fetchall()
        return [dict(r) for r in rows]

    def archive_development_events(
        self, older_than_days: int = 90, keep_recent: int = 300
    ) -> int:
        cutoff = (
            datetime.now() - timedelta(days=max(1, int(older_than_days)))
        ).strftime("%Y-%m-%d %H:%M:%S")
        archived_at = time.strftime("%Y-%m-%d %H:%M:%S")
        with _conn() as con:
            rows = con.execute(
                """SELECT * FROM development_events
                   WHERE ts < ? AND id NOT IN (
                       SELECT id FROM development_events
                       ORDER BY id DESC LIMIT ?
                   )""",
                (cutoff, max(1, int(keep_recent))),
            ).fetchall()
            if not rows:
                return 0
            for row in rows:
                con.execute(
                    "INSERT OR REPLACE INTO development_events_archive "
                    "(id, ts, event_type, target_kind, target_key, delta, "
                    "confidence_before, confidence_after, evidence_refs, "
                    "contradiction_refs, reason, requires_review, "
                    "reviewed_by_owner, metadata, archived_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["id"],
                        row["ts"],
                        row["event_type"],
                        row["target_kind"],
                        row["target_key"],
                        row["delta"],
                        row["confidence_before"],
                        row["confidence_after"],
                        row["evidence_refs"],
                        row["contradiction_refs"],
                        row["reason"],
                        row["requires_review"],
                        row["reviewed_by_owner"],
                        row["metadata"],
                        archived_at,
                    ),
                )
            ids = [row["id"] for row in rows]
            placeholders = ",".join("?" for _ in ids)
            con.execute(
                f"DELETE FROM development_events WHERE id IN ({placeholders})",
                ids,
            )
        AuditLog.memory_write("Memory", "archive", f"development_events:{len(rows)}")
        return len(rows)

    def recent_archived_development_events(self, n: int = 20) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM development_events_archive "
                "ORDER BY archived_at DESC LIMIT ?",
                (max(1, int(n)),),
            ).fetchall()
        return [dict(r) for r in rows]

    def decay_stats(self) -> dict:
        with _conn() as con:
            n_active = con.execute("SELECT COUNT(*) FROM development_events").fetchone()[0]
            n_archive = con.execute(
                "SELECT COUNT(*) FROM development_events_archive"
            ).fetchone()[0]
            n_weak = con.execute(
                """SELECT COUNT(*) FROM facts
                   WHERE confidence < ? AND confidence >= ?""",
                (0.75, MIN_RETRIEVAL_CONFIDENCE),
            ).fetchone()[0]
        return {
            "development_active": int(n_active),
            "development_archived": int(n_archive),
            "weak_facts": int(n_weak),
            "min_retrieval_confidence": MIN_RETRIEVAL_CONFIDENCE,
        }

    # ── Task-Checkpoints ──────────────────────────────────────────────────────
    def save_task_checkpoint(
        self,
        task_id: str,
        state_name: str,
        input_snapshot: dict | None = None,
        tool_snapshot: dict | None = None,
        result_snapshot: dict | None = None,
        memory_refs: list | None = None,
        side_effect_refs: list | None = None,
    ) -> int:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with _conn() as con:
            cur = con.execute(
                "INSERT INTO task_checkpoints "
                "(task_id, ts, state_name, input_snapshot, tool_snapshot, "
                "result_snapshot, memory_refs, side_effect_refs) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    ts,
                    state_name,
                    json.dumps(input_snapshot or {}, ensure_ascii=False),
                    json.dumps(tool_snapshot or {}, ensure_ascii=False),
                    json.dumps(result_snapshot or {}, ensure_ascii=False),
                    json.dumps(memory_refs or [], ensure_ascii=False),
                    json.dumps(side_effect_refs or [], ensure_ascii=False),
                ),
            )
            return int(cur.lastrowid)

    def get_latest_checkpoint(self, task_id: str) -> dict | None:
        with _conn() as con:
            row = con.execute(
                "SELECT * FROM task_checkpoints WHERE task_id=? "
                "ORDER BY checkpoint_id DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_checkpoint_by_id(self, checkpoint_id: int) -> dict | None:
        with _conn() as con:
            row = con.execute(
                "SELECT * FROM task_checkpoints WHERE checkpoint_id=?",
                (int(checkpoint_id),),
            ).fetchone()
        return dict(row) if row else None

    def list_checkpoints(self, task_id: str, limit: int = 20) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM task_checkpoints WHERE task_id=? "
                "ORDER BY checkpoint_id DESC LIMIT ?",
                (task_id, max(1, int(limit))),
            ).fetchall()
        return [dict(r) for r in rows]


# ── Singleton ──────────────────────────────────────────────────────────────────
_memory: Optional[Memory] = None

def get_memory() -> Memory:
    global _memory
    if _memory is None:
        _memory = Memory()
    return _memory
