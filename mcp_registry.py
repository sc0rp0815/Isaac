from __future__ import annotations

"""Isaac – MCP Registry
Leichtgewichtige MCP-nahe Registry mit lokalen Resource-/Tool-/Prompt-Handlern.
"""

from typing import Dict, Any, List, Callable


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
        }

    def invoke_tool(self, name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            return {"ok": False, "error": f"Unknown MCP tool: {name}"}
        handler = tool.get("_handler")
        if handler is None:
            return {"ok": False, "error": f"Tool has no handler: {name}"}
        try:
            result = handler(**(arguments or {}))
            return {"ok": True, "tool": name, "result": result}
        except TypeError as e:
            return {"ok": False, "tool": name, "error": f"Argument error: {e}"}
        except Exception as e:
            return {"ok": False, "tool": name, "error": str(e)}

    def read_resource(self, uri: str, **kwargs) -> Dict[str, Any]:
        res = self._resources.get(uri)
        if not res:
            return {"ok": False, "error": f"Unknown MCP resource: {uri}"}
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
        {"description": "Liest den Status eines Isaac-Tasks.", "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}}}},
        handler=lambda task_id="", **kwargs: __import__("executor").get_executor().get_task(task_id).to_dict() if task_id and __import__("executor").get_executor().get_task(task_id) else {"ok": True, "tasks": __import__("executor").get_executor().all_tasks(10)},
    )
    reg.register_tool(
        "isaac.audit_recent",
        {"description": "Liest die letzten Audit-Einträge.", "inputSchema": {"type": "object", "properties": {"n": {"type": "integer"}}}},
        handler=lambda n=20, **kwargs: __import__("audit").AuditLog.recent(int(n)),
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
        handler=lambda topic="", **kwargs: f"Bestimme den nächsten Recherche-Schritt für: {topic}. Konzentriere dich auf fehlende Fakten, Quellen oder offene Fragen.",
    )
    return reg
