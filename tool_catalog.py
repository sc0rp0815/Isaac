from __future__ import annotations

"""Isaac – Local Tool Catalog
Vordefinierte lokale Tool-Schnittstellen, die ohne schweren Zusatz-Stack
im Dashboard angeboten und in die Registry installiert werden können.
"""

from copy import deepcopy
from typing import Any

LOCAL_TOOL_CATALOG: list[dict[str, Any]] = [
    {
        "catalog_id": "local_search_duckduckgo",
        "name": "DuckDuckGo Instant Search",
        "kind": "search",
        "category": "suche",
        "description": "Leichtgewichtige Websuche über die DuckDuckGo-Instant-Answer-Schnittstelle.",
        "base_url": "https://api.duckduckgo.com/",
        "query_param": "q",
        "method": "GET",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": True,
        "priority": 72,
        "trust": 58.0,
        "metadata": {"return_format": "json", "source": "catalog", "local": True},
    },
    {
        "catalog_id": "local_http_json_adapter",
        "name": "HTTP JSON Adapter",
        "kind": "api",
        "category": "general",
        "description": "Generischer lokaler HTTP/JSON-Adapter für REST-Tools.",
        "base_url": "http://127.0.0.1:8080/api/tool",
        "endpoint": "",
        "query_param": "q",
        "method": "POST",
        "size_mb": 0.1,
        "install_mode": "register_only",
        "active": False,
        "priority": 60,
        "trust": 50.0,
        "metadata": {"source": "catalog", "local": True},
    },
    {
        "catalog_id": "local_script_runner",
        "name": "Local Script Runner",
        "kind": "script",
        "category": "code",
        "description": "Bindet lokale Skripte als Isaac-Tool ein. Geeignet für kleine Helfer in Termux/Alpine.",
        "script_path": "./tools/example_tool.sh",
        "method": "EXEC",
        "size_mb": 0.0,
        "install_mode": "register_only",
        "active": False,
        "priority": 64,
        "trust": 52.0,
        "metadata": {"source": "catalog", "local": True, "requires_path_edit": True},
    },
    {
        "catalog_id": "local_browser_chat_bridge",
        "name": "Browser Chat Bridge",
        "kind": "browser_chat",
        "category": "suche",
        "description": "Bridge für browsergestützte Chat-/Recherche-Instanzen.",
        "website_url": "https://example.local/browser-chat",
        "method": "BROWSER",
        "size_mb": 0.4,
        "install_mode": "register_only",
        "active": False,
        "priority": 68,
        "trust": 50.0,
        "metadata": {"source": "catalog", "local": True},
    },
    {
        "catalog_id": "local_mcp_bridge",
        "name": "MCP Bridge",
        "kind": "mcp",
        "category": "integration",
        "description": "MCP-nahe Bridge für Tools, Resources und Prompts über eine lokale HTTP-Bridge.",
        "base_url": "http://127.0.0.1:8766/api/mcp",
        "method": "POST",
        "size_mb": 0.2,
        "install_mode": "register_only",
        "active": False,
        "priority": 70,
        "trust": 54.0,
        "metadata": {"source": "catalog", "local": True, "mcp_like": True, "features": ["tools", "resources", "prompts"]},
    },
]


def list_local_tool_catalog() -> list[dict[str, Any]]:
    return [deepcopy(item) for item in LOCAL_TOOL_CATALOG]


def get_catalog_item(catalog_id: str) -> dict[str, Any] | None:
    for item in LOCAL_TOOL_CATALOG:
        if item["catalog_id"] == catalog_id:
            return deepcopy(item)
    return None


def registry_payload_from_catalog(catalog_id: str) -> dict[str, Any]:
    item = get_catalog_item(catalog_id)
    if not item:
        raise KeyError(f"Unbekannter Katalogeintrag: {catalog_id}")
    payload = deepcopy(item)
    payload.pop("catalog_id", None)
    payload.pop("size_mb", None)
    payload.pop("install_mode", None)
    meta = dict(payload.get("metadata") or {})
    meta["catalog_id"] = catalog_id
    payload["metadata"] = meta
    return payload
