from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config import DATA_DIR

STATE_PATH = DATA_DIR / "task_tool_states.json"


def _ts() -> float:
    return time.time()


@dataclass
class ToolCallRecord:
    ts: float
    source: str
    identifier: str
    name: str
    feature_type: str = "tool"
    ok: bool = False
    category: str = "general"
    kind: str = ""
    note: str = ""
    status_code: int | None = None


@dataclass
class TaskToolState:
    task_id: str
    strategy: str = "general"
    status: str = "idle"
    preferred_categories: list[str] = field(default_factory=list)
    preferred_kinds: list[str] = field(default_factory=list)
    selected_tool_id: str = ""
    selected_tool_name: str = ""
    selected_source: str = ""
    used_tool_ids: list[str] = field(default_factory=list)
    tool_history: list[ToolCallRecord] = field(default_factory=list)
    next_inputs: list[str] = field(default_factory=list)
    last_tool_output: str = ""
    last_tool_summary: str = ""
    resume_count: int = 0
    created_at: float = field(default_factory=_ts)
    updated_at: float = field(default_factory=_ts)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tool_history"] = [asdict(x) for x in self.tool_history[-12:]]
        data["next_inputs"] = self.next_inputs[-6:]
        return data


class TaskToolStateStore:
    def __init__(self, path: Path = STATE_PATH):
        self.path = path
        self._items: dict[str, TaskToolState] = {}
        self._load()

    def _load(self):
        if not self.path.exists():
            self._save()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            items: dict[str, TaskToolState] = {}
            for row in raw:
                hist = [ToolCallRecord(**x) for x in row.get("tool_history", [])]
                row = dict(row)
                row["tool_history"] = hist
                items[row["task_id"]] = TaskToolState(**row)
            self._items = items
        except Exception:
            self._items = {}
            self._save()

    def _save(self):
        payload = [item.to_dict() for item in sorted(self._items.values(), key=lambda x: x.updated_at, reverse=True)[:300]]
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_or_create(self, task_id: str, prompt: str = "") -> TaskToolState:
        item = self._items.get(task_id)
        if item is None:
            item = TaskToolState(task_id=task_id)
            self._items[task_id] = item
            self._derive_strategy(item, prompt)
            self._save()
        elif prompt:
            self._derive_strategy(item, prompt)
        return item

    def get(self, task_id: str) -> TaskToolState | None:
        return self._items.get(task_id)

    def _derive_strategy(self, item: TaskToolState, prompt: str):
        p = (prompt or "").lower()
        categories: list[str] = []
        kinds: list[str] = []
        strategy = "general"
        if any(k in p for k in ("suche", "search", "recherche", "internet", "web", "browser")):
            strategy = "research"
            categories.extend(["suche", "general"])
            kinds.extend(["search", "browser_chat", "mcp"]) 
        if any(k in p for k in ("api", "schnittstelle", "integration", "mcp", "tool")):
            strategy = "integration"
            categories.extend(["integration", "general"])
            kinds.extend(["mcp", "api"])
        if any(k in p for k in ("code", "python", "script", "github")):
            strategy = "code"
            categories.extend(["code", "general"])
            kinds.extend(["script", "api", "mcp"])
        if any(k in p for k in ("datei", "file", "resource", "quelle")):
            categories.extend(["resource", "general"])
        if any(k in p for k in ("wetter", "weather")):
            strategy = "research"
            categories.extend(["wetter", "suche", "general"])
            kinds.extend(["search", "api", "mcp"])
        if not categories:
            categories = ["general"]
        if not kinds:
            kinds = ["mcp", "api", "search"]
        item.strategy = strategy
        item.preferred_categories = list(dict.fromkeys(categories))[:5]
        item.preferred_kinds = list(dict.fromkeys(kinds))[:5]
        item.updated_at = _ts()

    def mark_resume(self, task_id: str):
        item = self.get_or_create(task_id)
        item.resume_count += 1
        item.status = "resumed"
        item.updated_at = _ts()
        self._save()
        return item

    def set_selected(self, task_id: str, source: str, identifier: str, name: str):
        item = self.get_or_create(task_id)
        item.selected_source = source
        item.selected_tool_id = identifier
        item.selected_tool_name = name
        if identifier and identifier not in item.used_tool_ids:
            item.used_tool_ids.append(identifier)
            item.used_tool_ids = item.used_tool_ids[-24:]
        item.status = "tool_selected"
        item.updated_at = _ts()
        self._save()
        return item

    def record_call(self, task_id: str, *, source: str, identifier: str, name: str,
                    feature_type: str = "tool", ok: bool = False, category: str = "general",
                    kind: str = "", note: str = "", status_code: int | None = None,
                    output: str = ""):
        item = self.get_or_create(task_id)
        item.tool_history.append(ToolCallRecord(
            ts=_ts(), source=source, identifier=identifier, name=name,
            feature_type=feature_type, ok=ok, category=category, kind=kind,
            note=note[:240], status_code=status_code,
        ))
        item.tool_history = item.tool_history[-40:]
        item.last_tool_output = (output or "")[:3000]
        item.last_tool_summary = self._summarize_output(output)
        item.status = "tool_ok" if ok else "tool_failed"
        item.updated_at = _ts()
        self._save()
        return item

    def add_next_input(self, task_id: str, text: str):
        text = (text or "").strip()
        if not text:
            return self.get_or_create(task_id)
        item = self.get_or_create(task_id)
        if text not in item.next_inputs:
            item.next_inputs.append(text[:1800])
            item.next_inputs = item.next_inputs[-8:]
        item.updated_at = _ts()
        self._save()
        return item

    def pop_next_input(self, task_id: str) -> str:
        item = self.get_or_create(task_id)
        if not item.next_inputs:
            return ""
        value = item.next_inputs.pop(0)
        item.updated_at = _ts()
        self._save()
        return value

    def set_status(self, task_id: str, status: str):
        item = self.get_or_create(task_id)
        item.status = status
        item.updated_at = _ts()
        self._save()
        return item

    def export_for_tasks(self, task_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
        task_ids = task_ids or list(self._items.keys())
        out: dict[str, dict[str, Any]] = {}
        for task_id in task_ids:
            item = self._items.get(task_id)
            if item:
                out[task_id] = item.to_dict()
        return out

    def generate_next_input(self, task_id: str, base_prompt: str, tool_name: str, tool_output: str) -> str:
        summary = self._summarize_output(tool_output)
        if not summary:
            return ""
        next_input = (
            f"Arbeite an der ursprünglichen Aufgabe weiter: {base_prompt[:700]}\n\n"
            f"Nutze dieses neue Werkzeug-Ergebnis von {tool_name}:\n{summary}\n\n"
            "Leite daraus den nächsten konkreten Schritt ab, schließe Lücken und arbeite nur mit den relevanten neuen Informationen weiter."
        )
        self.add_next_input(task_id, next_input)
        return next_input

    def _summarize_output(self, output: str) -> str:
        raw = (output or "").strip()
        if not raw:
            return ""
        raw = raw.replace("\r", "")
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:
            return raw[:700]
        if len(lines) == 1:
            return lines[0][:700]
        head = lines[:8]
        return "\n".join(head)[:900]


_store: TaskToolStateStore | None = None


def get_task_tool_state_store() -> TaskToolStateStore:
    global _store
    if _store is None:
        _store = TaskToolStateStore()
    return _store
