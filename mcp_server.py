from __future__ import annotations

"""Isaac – MCP Server
HTTP-Bridge und stdio-Transport für Isaacs MCP-Tools/Resources/Prompts.
"""

import json
import sys

from flask import Blueprint, jsonify, request

from mcp_jsonrpc import get_jsonrpc_handler
from mcp_registry import get_mcp_registry

mcp_api = Blueprint("mcp_api", __name__, url_prefix="/api/mcp")


def _registry():
    return get_mcp_registry()


@mcp_api.get("/")
def root():
    reg = _registry()
    return jsonify({
        "ok": True,
        "transport": ["rest", "jsonrpc"],
        "jsonrpc_endpoint": "/api/mcp/jsonrpc",
        "capabilities": reg.capabilities(),
        "tools": reg.tools(),
        "resources": reg.resources(),
        "prompts": reg.prompts(),
    })


@mcp_api.post("/jsonrpc")
def jsonrpc():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error"},
        }), 400
    try:
        result = get_jsonrpc_handler(_registry()).handle_payload(payload)
    except Exception as exc:
        return jsonify({
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32603, "message": str(exc)},
        }), 500
    if isinstance(result, list):
        return jsonify(result), 200
    return jsonify(result), 200


@mcp_api.get("/capabilities")
def capabilities():
    return jsonify({"ok": True, "capabilities": _registry().capabilities()})


@mcp_api.get("/resources")
def resources():
    reg = _registry()
    return jsonify({"ok": True, "resources": reg.resources()})


@mcp_api.post("/resource/read")
def read_resource():
    data = request.get_json(silent=True) or {}
    uri = (data.get("uri") or "").strip()
    kwargs = dict(data.get("params") or {})
    result = _registry().read_resource(uri, **kwargs)
    return jsonify(result), (200 if result.get("ok") else 404)


@mcp_api.get("/prompts")
def prompts():
    reg = _registry()
    return jsonify({"ok": True, "prompts": reg.prompts()})


@mcp_api.post("/prompts/get")
def get_prompt():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    args = dict(data.get("arguments") or {})
    result = _registry().get_prompt(name, args)
    return jsonify(result), (200 if result.get("ok") else 404)


@mcp_api.get("/tools")
def tools():
    reg = _registry()
    return jsonify({"ok": True, "tools": reg.tools()})


@mcp_api.post("/tools/invoke")
def invoke_tool():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    args = dict(data.get("arguments") or {})
    result = _registry().invoke_tool(name, args)
    return jsonify(result), (200 if result.get("ok") else 400)


def run_stdio_transport() -> int:
    """Newline-delimited JSON-RPC über stdin/stdout (MCP-stdio-Transport)."""
    handler = get_jsonrpc_handler(_registry())
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }) + "\n")
            sys.stdout.flush()
            continue
        try:
            result = handler.handle_payload(payload)
        except Exception as exc:
            result = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(exc)},
            }
        if isinstance(result, list):
            for item in result:
                sys.stdout.write(json.dumps(item, ensure_ascii=False) + "\n")
        else:
            sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        raise SystemExit(run_stdio_transport())
    print("Isaac MCP Server Blueprint – mount mcp_api or run with --stdio", file=sys.stderr)