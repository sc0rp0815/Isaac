from __future__ import annotations
import json, time, uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TOOLS_FILE = DATA_DIR / "tools_registry.json"

def _ts() -> float:
    return time.time()

@dataclass
class ToolEntry:
    tool_id: str
    name: str
    kind: str                  # api | browser_chat | search | web_tool | script
    category: str = "general"
    description: str = ""
    base_url: str = ""
    endpoint: str = ""
    website_url: str = ""
    script_path: str = ""
    auth_type: str = "none"    # none | header | query
    auth_field: str = ""
    auth_prefix: str = ""
    secret_ref: str = ""
    query_param: str = "q"
    method: str = "GET"
    active: bool = True
    priority: int = 50
    trust: float = 50.0
    success_count: int = 0
    failure_count: int = 0
    last_status: str = "unknown"
    last_test_at: float = 0.0
    created_at: float = field(default_factory=_ts)
    updated_at: float = field(default_factory=_ts)
    metadata: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return round((self.success_count / total) * 100.0, 2) if total else 0.0

class ToolRegistry:
    def __init__(self, path: Path = TOOLS_FILE):
        self.path = path
        self._tools: dict[str, ToolEntry] = {}
        self._load()

    def _load(self):
        if not self.path.exists():
            self._save()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._tools = {x["tool_id"]: ToolEntry(**x) for x in raw}
        except Exception:
            self._tools = {}
            self._save()

    def _save(self):
        payload = [asdict(t) for t in sorted(self._tools.values(), key=lambda x: (-x.priority, -x.trust, x.name.lower()))]
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_tools(self, active_only: bool = False) -> list[dict]:
        items = list(self._tools.values())
        if active_only:
            items = [t for t in items if t.active]
        rows = []
        for t in items:
            row = asdict(t)
            row["success_rate"] = t.success_rate
            rows.append(row)
        return sorted(rows, key=lambda x: (-x["priority"], -x["trust"], x["name"].lower()))

    def get(self, tool_id: str) -> Optional[ToolEntry]:
        return self._tools.get(tool_id)

    def add(self, data: dict) -> ToolEntry:
        tool_id = data.get("tool_id") or f"tool_{uuid.uuid4().hex[:10]}"
        entry = ToolEntry(
            tool_id=tool_id,
            name=data["name"].strip(),
            kind=data["kind"].strip(),
            category=(data.get("category") or "general").strip(),
            description=(data.get("description") or "").strip(),
            base_url=(data.get("base_url") or "").strip(),
            endpoint=(data.get("endpoint") or "").strip(),
            website_url=(data.get("website_url") or "").strip(),
            script_path=(data.get("script_path") or "").strip(),
            auth_type=(data.get("auth_type") or "none").strip(),
            auth_field=(data.get("auth_field") or "").strip(),
            auth_prefix=(data.get("auth_prefix") or "").strip(),
            secret_ref=(data.get("secret_ref") or "").strip(),
            query_param=(data.get("query_param") or "q").strip(),
            method=(data.get("method") or "GET").strip().upper(),
            active=bool(data.get("active", True)),
            priority=int(data.get("priority", 50)),
            trust=float(data.get("trust", 50.0)),
            metadata=dict(data.get("metadata", {})),
        )
        self._tools[tool_id] = entry
        self._save()
        return entry

    def update(self, tool_id: str, patch: dict) -> ToolEntry:
        t = self._require(tool_id)
        for key, value in patch.items():
            if hasattr(t, key):
                setattr(t, key, value)
        t.updated_at = _ts()
        self._save()
        return t

    def delete(self, tool_id: str) -> bool:
        ok = tool_id in self._tools
        if ok:
            self._tools.pop(tool_id, None)
            self._save()
        return ok

    def record(self, tool_id: str, ok: bool, note: str = "") -> ToolEntry:
        t = self._require(tool_id)
        if ok:
            t.success_count += 1
            t.trust = min(100.0, t.trust + 1.0)
            t.last_status = "ok"
        else:
            t.failure_count += 1
            t.trust = max(0.0, t.trust - 2.0)
            t.last_status = "failed"
        t.last_test_at = _ts()
        if note:
            t.notes.append(note[:280])
            t.notes = t.notes[-25:]
        t.updated_at = _ts()
        self._save()
        return t

    def pick(self, category: str = "", kind: str = "") -> Optional[ToolEntry]:
        tools = [t for t in self._tools.values() if t.active]
        if category:
            tools = [t for t in tools if t.category == category]
        if kind:
            tools = [t for t in tools if t.kind == kind]
        if not tools:
            return None
        return sorted(tools, key=lambda x: (x.trust, x.priority, x.success_rate), reverse=True)[0]

    def _require(self, tool_id: str) -> ToolEntry:
        t = self._tools.get(tool_id)
        if not t:
            raise KeyError(f"Tool nicht gefunden: {tool_id}")
        return t

_registry = None

def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
