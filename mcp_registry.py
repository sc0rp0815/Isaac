from __future__ import annotations

"""Isaac – MCP Registry
Leichtgewichtige MCP-nahe Registry mit lokalen Resource-/Tool-/Prompt-Handlern.
"""

import asyncio
from typing import Dict, Any, List, Callable, Optional
from result_contract import ensure_result_contract

# Privilege-Mapping: MCP-Name -> benötigte Privilege-Aktion
MCP_TOOL_PRIVILEGES: Dict[str, str] = {
    "isaac.task_status": "read_memory",
    "isaac.audit_recent": "read_audit",
    "isaac.query_memory": "read_memory",
    "isaac.start_task": "chat_response",
    "isaac.search_web": "internet_search",
    "isaac.run_browser_action": "browser_navigate",
}

MCP_RESOURCE_PRIVILEGES: Dict[str, str] = {
    "resource://constitution": "read_memory",
    "resource://self-model": "read_memory",
    "resource://memory/blocks": "read_memory",
    "resource://audit/tail": "read_audit",
    "isaac://tasks/recent": "read_memory",
    "isaac://tools/registry": "read_memory",
}

MCP_CONSTITUTION_GATED_TOOLS = frozenset({
    "isaac.search_web",
    "isaac.run_browser_action",
    "isaac.start_task",
})


def _handler_result_contract(name: str, result: Any) -> Dict[str, Any]:
    if isinstance(result, dict) and (
        "output" in result or "content" in result or "error" in result or "metadata" in result
    ):
        return ensure_result_contract(result, source=f"mcp_registry:{name}")
    return ensure_result_contract(
        {"ok": True, "output": result, "metadata": {"tool": name}},
        source=f"mcp_registry:{name}",
    )


class MCPRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._resources: Dict[str, Dict[str, Any]] = {}
        self._prompts: Dict[str, Dict[str, Any]] = {}

    def register_tool(self, name: str, schema: Dict[str, Any], handler: Callable[..., Any] | None = None):
        entry = dict(schema)
        if handler is not None:
            entry["_handler"] = handler
        self._tools[name] = entry

    def register_resource(self, uri: str, schema: Dict[str, Any], handler: Callable[..., Any] | None = None):
        entry = dict(schema)
        if handler is not None:
            entry["_handler"] = handler
        self._resources[uri] = entry

    def register_prompt(self, name: str, schema: Dict[str, Any], handler: Callable[..., Any] | None = None):
        entry = dict(schema)
        if handler is not None:
            entry["_handler"] = handler
        self._prompts[name] = entry

    def tools(self) -> List[Dict[str, Any]]:
        out = []
        for k, v in sorted(self._tools.items()):
            item = {"name": k, **v}
            item.pop("_handler", None)
            out.append(item)
        return out

    def resources(self) -> List[Dict[str, Any]]:
        out = []
        for k, v in sorted(self._resources.items()):
            item = {"uri": k, **v}
            item.pop("_handler", None)
            out.append(item)
        return out

    def prompts(self) -> List[Dict[str, Any]]:
        out = []
        for k, v in sorted(self._prompts.items()):
            item = {"name": k, **v}
            item.pop("_handler", None)
            out.append(item)
        return out

    def capabilities(self) -> Dict[str, Any]:
        return {
            "tools": sorted(self._tools.keys()),
            "resources": sorted(self._resources.keys()),
            "prompts": sorted(self._prompts.keys()),
            "resource_count": len(self._resources),
            "tool_count": len(self._tools),
            "prompt_count": len(self._prompts),
            "features": ["tools", "resources", "prompts"],
            "tool_privileges": dict(MCP_TOOL_PRIVILEGES),
            "resource_privileges": dict(MCP_RESOURCE_PRIVILEGES),
        }

    def invoke_tool(self, name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            return {"ok": False, "error": f"Unknown MCP tool: {name}"}
        denied = _authorize_mcp_tool(name)
        if denied:
            return denied
        if name in MCP_CONSTITUTION_GATED_TOOLS:
            denied = _constitution_gate_mcp_tool(name)
            if denied:
                return denied
        handler = tool.get("_handler")
        if handler is None:
            return {"ok": False, "error": f"Tool has no handler: {name}"}
        try:
            result = handler(**(arguments or {}))
            return _handler_result_contract(name, result)
        except TypeError as e:
            return ensure_result_contract({"ok": False, "error": f"Argument error: {e}", "metadata": {"tool": name}}, source=f"mcp_registry:{name}")
        except Exception as e:
            return ensure_result_contract({"ok": False, "error": str(e), "metadata": {"tool": name}}, source=f"mcp_registry:{name}")

    def read_resource(self, uri: str, **kwargs) -> Dict[str, Any]:
        res = self._resources.get(uri)
        if not res:
            return {"ok": False, "error": f"Unknown MCP resource: {uri}"}
        denied = _authorize_mcp_resource(uri)
        if denied:
            return denied
        handler = res.get("_handler")
        if handler is None:
            return {"ok": False, "error": f"Resource has no handler: {uri}"}
        try:
            value = handler(**kwargs)
            return {"ok": True, "uri": uri, "resource": value}
        except TypeError as e:
            return {"ok": False, "uri": uri, "error": f"Argument error: {e}"}
        except Exception as e:
            return {"ok": False, "uri": uri, "error": str(e)}

    def get_prompt(self, name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        entry = self._prompts.get(name)
        if not entry:
            return {"ok": False, "error": f"Unknown MCP prompt: {name}"}
        handler = entry.get("_handler")
        if handler is None:
            return {"ok": False, "error": f"Prompt has no handler: {name}"}
        try:
            prompt = handler(**(arguments or {}))
            return {"ok": True, "name": name, "prompt": prompt}
        except TypeError as e:
            return {"ok": False, "name": name, "error": f"Argument error: {e}"}
        except Exception as e:
            return {"ok": False, "name": name, "error": str(e)}


def _authorize_mcp_tool(name: str) -> Optional[Dict[str, Any]]:
    from privilege import get_gate, isaac_ctx

    action = MCP_TOOL_PRIVILEGES.get(name, "chat_response")
    ok, reason = get_gate().authorize(action, isaac_ctx("MCP", f"MCP tool invoke: {name}"))
    if ok:
        return None
    return ensure_result_contract(
        {
            "ok": False,
            "error": reason,
            "metadata": {"tool": name, "required_privilege": action},
        },
        source="mcp_registry:privilege",
    )


def _authorize_mcp_resource(uri: str) -> Optional[Dict[str, Any]]:
    from privilege import get_gate, isaac_ctx

    action = MCP_RESOURCE_PRIVILEGES.get(uri, "read_memory")
    ok, reason = get_gate().authorize(action, isaac_ctx("MCP", f"MCP resource read: {uri}"))
    if ok:
        return None
    return {"ok": False, "uri": uri, "error": reason, "required_privilege": action}


def _constitution_gate_mcp_tool(name: str) -> Optional[Dict[str, Any]]:
    from constitution import get_constitution
    from audit import AuditLog

    verdict = get_constitution().validate_action(
        "tool_invoke",
        {"outside_effect": True, "audit_logged": True, "risk": "normal"},
    )
    if verdict.get("allowed"):
        return None
    blocked = verdict.get("blocked_by", [])
    AuditLog.action("Constitution", "mcp_tool_blocked", f"{name}:{','.join(blocked)}", erfolg=False)
    return ensure_result_contract(
        {
            "ok": False,
            "error": f"Verfassung blockiert MCP-Tool: {', '.join(blocked)}",
            "metadata": {"tool": name, "blocked_by": blocked},
        },
        source="mcp_registry:constitution",
    )


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("MCP handler cannot run async coroutine inside active event loop")


def _read_constitution(**kwargs) -> Dict[str, Any]:
    from constitution import get_constitution

    c = get_constitution()
    return {"version": c.version(), "summary": c.summary(), "export": c.export()}


def _read_self_model(**kwargs) -> Dict[str, Any]:
    from self_model import get_self_model

    return get_self_model().snapshot()


def _read_memory_blocks(limit: int = 20, **kwargs) -> Dict[str, Any]:
    from memory import get_memory

    mem = get_memory()
    limit = max(1, min(int(limit), 50))
    blocks: list[dict] = []
    for directive in mem.get_directives()[:limit]:
        blocks.append(
            {
                "block_type": "directive",
                "key": directive.get("id", ""),
                "content": directive.get("text", ""),
                "priority": directive.get("priority", 0),
            }
        )
    for key, value in list(mem.all_facts().items())[:limit]:
        blocks.append({"block_type": "fact", "key": key, "content": value})
    for event in mem.recent_development_events(min(limit, 10)):
        blocks.append(
            {
                "block_type": "development",
                "key": event.get("target_key", ""),
                "content": event.get("reason", ""),
                "delta": event.get("delta", 0.0),
            }
        )
    return {"blocks": blocks[:limit], "count": len(blocks[:limit])}


def _read_audit_tail(n: int = 50, **kwargs) -> list[dict]:
    from audit import AuditLog

    return AuditLog.recent(max(1, min(int(n), 200)))


def _query_memory(query: str = "", limit: int = 6, **kwargs) -> Dict[str, Any]:
    from memory import get_memory

    mem = get_memory()
    q = (query or "").strip()
    ctx = mem.build_retrieval_context(q or "status", n_history=min(int(limit), 10))
    return ctx.as_dict()


def _start_task(prompt: str = "", typ: str = "chat", **kwargs) -> Dict[str, Any]:
    from executor import get_executor, TaskType

    text = (prompt or "").strip()
    if not text:
        return {"ok": False, "error": "prompt fehlt"}
    type_map = {
        "chat": TaskType.CHAT,
        "search": TaskType.SEARCH,
        "code": TaskType.CODE,
    }
    task_type = type_map.get((typ or "chat").lower(), TaskType.CHAT)
    task = get_executor().create_task(task_type, text, beschreibung=text[:120])
    return {"ok": True, "task_id": task.id, "status": task.status.value, "typ": task.typ.value}


def _search_web(query: str = "", **kwargs) -> Dict[str, Any]:
    from search import get_search

    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "query fehlt"}

    async def _do():
        result = await get_search().search(q, max_hits=5, load_fulltext=False)
        return {
            "query": result.query,
            "hits": len(result.hits),
            "fehler": result.fehler[:3],
            "summary": result.als_kontext(max_hits=5)[:1500],
        }

    payload = _run_async(_do())
    return {"ok": True, "query": q, "result": payload}


def _run_browser_action(action: str = "open", url: str = "", **kwargs) -> Dict[str, Any]:
    from browser import get_browser

    target = (url or "").strip()
    if not target:
        return {"ok": False, "error": "url fehlt"}
    browser = get_browser()
    if not browser._browser_allowed(target):
        return {"ok": False, "error": "Browser deaktiviert oder URL nicht erlaubt"}
    if action != "open":
        return {"ok": False, "error": f"Unbekannte Browser-Aktion: {action}"}
    return {
        "ok": True,
        "action": action,
        "url": target,
        "note": "Browser-Flow ist vorbereitet; Live-Ausführung erfolgt über Executor/BrowserManager.",
    }


_registry: MCPRegistry | None = None


def get_mcp_registry() -> MCPRegistry:
    global _registry
    if _registry is None:
        _registry = MCPRegistry()
        _register_defaults(_registry)
    return _registry


def _register_defaults(reg: MCPRegistry):
    if reg.tools():
        return reg

    reg.register_tool(
        "isaac.task_status",
        {
            "description": "Liest den Status eines Isaac-Tasks.",
            "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}}},
            "required_privilege": MCP_TOOL_PRIVILEGES["isaac.task_status"],
        },
        handler=lambda task_id="", **kwargs: (
            __import__("executor").get_executor().get_task(task_id).to_dict()
            if task_id and __import__("executor").get_executor().get_task(task_id)
            else {"ok": True, "tasks": __import__("executor").get_executor().all_tasks(10)}
        ),
    )
    reg.register_tool(
        "isaac.audit_recent",
        {
            "description": "Liest die letzten Audit-Einträge.",
            "inputSchema": {"type": "object", "properties": {"n": {"type": "integer"}}},
            "required_privilege": MCP_TOOL_PRIVILEGES["isaac.audit_recent"],
        },
        handler=_read_audit_tail,
    )
    reg.register_tool(
        "isaac.query_memory",
        {
            "description": "Baut einen strukturierten Retrieval-Kontext für eine Anfrage.",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            },
            "required_privilege": MCP_TOOL_PRIVILEGES["isaac.query_memory"],
        },
        handler=_query_memory,
    )
    reg.register_tool(
        "isaac.start_task",
        {
            "description": "Erstellt einen neuen Isaac-Task (ohne automatische Ausführung).",
            "inputSchema": {
                "type": "object",
                "properties": {"prompt": {"type": "string"}, "typ": {"type": "string"}},
                "required": ["prompt"],
            },
            "required_privilege": MCP_TOOL_PRIVILEGES["isaac.start_task"],
        },
        handler=_start_task,
    )
    reg.register_tool(
        "isaac.search_web",
        {
            "description": "Führt eine Websuche über Isaacs Search-Modul aus.",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "required_privilege": MCP_TOOL_PRIVILEGES["isaac.search_web"],
        },
        handler=_search_web,
    )
    reg.register_tool(
        "isaac.run_browser_action",
        {
            "description": "Führt eine explizite Browser-Aktion aus.",
            "inputSchema": {
                "type": "object",
                "properties": {"action": {"type": "string"}, "url": {"type": "string"}},
                "required": ["url"],
            },
            "required_privilege": MCP_TOOL_PRIVILEGES["isaac.run_browser_action"],
        },
        handler=_run_browser_action,
    )

    reg.register_resource(
        "resource://constitution",
        {"description": "Isaac-Verfassung (Version, Summary, Export).", "mimeType": "application/json"},
        handler=_read_constitution,
    )
    reg.register_resource(
        "resource://self-model",
        {"description": "Explizites Isaac-Selbstmodell.", "mimeType": "application/json"},
        handler=_read_self_model,
    )
    reg.register_resource(
        "resource://memory/blocks",
        {"description": "Strukturierte Memory-Blöcke (Fakten, Direktiven, Entwicklung).", "mimeType": "application/json"},
        handler=_read_memory_blocks,
    )
    reg.register_resource(
        "resource://audit/tail",
        {"description": "Letzte Audit-Einträge.", "mimeType": "application/json"},
        handler=_read_audit_tail,
    )
    reg.register_resource(
        "isaac://tasks/recent",
        {"description": "Aktuelle und letzte Tasks als Resource."},
        handler=lambda limit=20, **kwargs: __import__("executor").get_executor().all_tasks(int(limit)),
    )
    reg.register_resource(
        "isaac://tools/registry",
        {"description": "Lokale Tool-Registry als Resource."},
        handler=lambda **kwargs: __import__("tool_registry").get_tool_registry().list_tools(),
    )
    reg.register_prompt(
        "tool.refine_input",
        {"description": "Erzeugt einen nächsten Arbeitsinput aus einem Tool-Ergebnis."},
        handler=lambda original_prompt="", tool_name="", tool_output="", **kwargs: (
            f"Arbeite an der Aufgabe weiter: {original_prompt}\n\n"
            f"Neues Ergebnis von {tool_name}:\n{tool_output[:1200]}\n\n"
            "Extrahiere den nächsten konkreten Schritt und fokussiere nur die neuen, relevanten Informationen."
        ),
    )
    reg.register_prompt(
        "research.next_step",
        {"description": "Erzeugt einen nächsten Recherche-Schritt."},
        handler=lambda topic="", **kwargs: (
            f"Bestimme den nächsten Recherche-Schritt für: {topic}. "
            "Konzentriere dich auf fehlende Fakten, Quellen oder offene Fragen."
        ),
    )
    return reg
