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
from pathlib import Path
from typing import Optional, Any
from contextlib import contextmanager

from config import DB_PATH, get_config
from audit  import AuditLog

log = logging.getLogger("Isaac.Memory")


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
    def set_fact(self, key: str, value: str, source: str = "",
                 confidence: float = 1.0) -> bool:
        """Schreibt oder aktualisiert eine Tatsache."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with _conn() as con:
            existing = con.execute(
                "SELECT id FROM facts WHERE key=?", (key,)
            ).fetchone()
            if existing:
                con.execute(
                    "UPDATE facts SET value=?, source=?, "
                    "confidence=?, updated=? WHERE key=?",
                    (value, source, confidence, ts, key)
                )
            else:
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

    def search_facts(self, query: str, limit: int = 10) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                """SELECT f.* FROM facts f
                   JOIN facts_fts ON facts_fts.rowid = f.id
                   WHERE facts_fts MATCH ?
                   ORDER BY f.confidence DESC LIMIT ?""",
                (query, limit)
            ).fetchall()
        return [dict(r) for r in rows]

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

    # ── Kontext-Aufbau für Relay ───────────────────────────────────────────────
    def build_context(self, query: str = "", n_history: int = 6) -> str:
        """Erstellt einen kompakten Kontext-Block — SQLite + semantisch."""
        parts = []

        # 1. Direktiven
        directives = self.get_directives()
        if directives:
            parts.append("[Steffen-Direktiven]")
            for d in directives[:5]:
                parts.append(f"  [{d['priority']}] {d['text']}")

        # 2. Relevante Fakten (SQLite)
        if query:
            facts = self.search_facts(query, limit=5)
            if facts:
                parts.append("[Relevante Fakten]")
                for f in facts:
                    parts.append(f"  {f['key']}: {f['value'][:100]}")

        # 3. Semantischer Kontext (ChromaDB wenn verfügbar)
        if query and self._vector.aktiv:
            vektor_ctx = self._vector.als_kontext(query)
            if vektor_ctx:
                parts.append(vektor_ctx)

        # 4. Konversations-Verlauf
        history = self.get_working_memory(n_history)
        if history:
            parts.append("[Konversations-Verlauf]")
            for h in history:
                role = "Steffen" if h["role"] == "steffen" else "Isaac"
                parts.append(f"  {role}: {h['text'][:150]}")

        return "\n".join(parts)

    # ── Statistiken ───────────────────────────────────────────────────────────
    def stats(self) -> dict:
        with _conn() as con:
            n_conv  = con.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            n_facts = con.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            n_tasks = con.execute("SELECT COUNT(*) FROM task_results").fetchone()[0]
            n_dir   = con.execute(
                "SELECT COUNT(*) FROM directives WHERE active=1"
            ).fetchone()[0]
        return {
            "conversations":  n_conv,
            "facts":          n_facts,
            "task_results":   n_tasks,
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


# ── Singleton ──────────────────────────────────────────────────────────────────
_memory: Optional[Memory] = None

def get_memory() -> Memory:
    global _memory
    if _memory is None:
        _memory = Memory()
    return _memory
