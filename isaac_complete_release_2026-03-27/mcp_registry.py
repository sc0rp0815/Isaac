from __future__ import annotations

"""Isaac – MCP Registry
Leichtgewichtige MCP-nahe Registry mit lokalen Resource-/Tool-Handlern.
Kein vollständiger MCP-Transport, aber kompatible Kernideen:
- Tools
- Resources
- Capabilities
- Invoke / Read
"""

from typing import Dict, Any, List, Callable


class MCPRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._resources: Dict[str, Dict[str, Any]] = {}

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

    def capabilities(self) -> Dict[str, Any]:
        return {
            "tools": sorted(self._tools.keys()),
            "resources": sorted(self._resources.keys()),
            "resource_count": len(self._resources),
            "tool_count": len(self._tools),
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


_registry: MCPRegistry | None = None


def get_mcp_registry() -> MCPRegistry:
    global _registry
    if _registry is None:
        _registry = MCPRegistry()
    return _registry
