from __future__ import annotations

from mcp_registry import get_mcp_registry, MCP_RESOURCE_PRIVILEGES, MCP_TOOL_PRIVILEGES


def run() -> dict:
    reg = get_mcp_registry()
    caps = reg.capabilities()
    cases = []

    for uri in (
        "resource://constitution",
        "resource://self-model",
        "resource://memory/blocks",
        "resource://audit/tail",
    ):
        present = uri in caps.get("resources", [])
        read_ok = False
        detail: dict = {}
        if present:
            result = reg.read_resource(uri, limit=5, n=5)
            read_ok = bool(result.get("ok"))
            detail = {"keys": sorted((result.get("resource") or {}).keys()) if isinstance(result.get("resource"), dict) else type(result.get("resource")).__name__}
        cases.append(
            {
                "name": f"resource_{uri.split('//')[-1].replace('/', '_')}",
                "ok": present and read_ok,
                "detail": detail,
            }
        )

    cases.append(
        {
            "name": "privilege_map_present",
            "ok": bool(caps.get("tool_privileges")) and bool(caps.get("resource_privileges")),
            "detail": {
                "tools": len(MCP_TOOL_PRIVILEGES),
                "resources": len(MCP_RESOURCE_PRIVILEGES),
            },
        }
    )

    query = reg.invoke_tool("isaac.query_memory", {"query": "Isaac status", "limit": 3})
    cases.append(
        {
            "name": "query_memory_tool",
            "ok": bool(query.get("ok")),
            "detail": {"has_output": "output" in query},
        }
    )

    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "mcp", "passed": passed, "total": len(cases), "cases": cases}


if __name__ == "__main__":
    import json

    print(json.dumps(run(), ensure_ascii=False, indent=2))