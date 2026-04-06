from __future__ import annotations

"""Isaac – MCP Server Blueprint
HTTP-Bridge für Isaacs MCP-nahe Tools/Resources/Prompts.
"""

from flask import Blueprint, jsonify, request
from mcp_registry import get_mcp_registry

mcp_api = Blueprint("mcp_api", __name__, url_prefix="/api/mcp")


@mcp_api.get("/")
def root():
    reg = get_mcp_registry()
    return jsonify({"ok": True, "capabilities": reg.capabilities(), "tools": reg.tools(), "resources": reg.resources(), "prompts": reg.prompts()})


@mcp_api.get("/capabilities")
def capabilities():
    return jsonify({"ok": True, "capabilities": get_mcp_registry().capabilities()})


@mcp_api.get("/resources")
def resources():
    reg = get_mcp_registry()
    return jsonify({"ok": True, "resources": reg.resources()})


@mcp_api.post("/resource/read")
def read_resource():
    data = request.get_json(silent=True) or {}
    uri = (data.get("uri") or "").strip()
    kwargs = dict(data.get("params") or {})
    result = get_mcp_registry().read_resource(uri, **kwargs)
    return jsonify(result), (200 if result.get("ok") else 404)


@mcp_api.get("/prompts")
def prompts():
    reg = get_mcp_registry()
    return jsonify({"ok": True, "prompts": reg.prompts()})


@mcp_api.post("/prompts/get")
def get_prompt():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    args = dict(data.get("arguments") or {})
    result = get_mcp_registry().get_prompt(name, args)
    return jsonify(result), (200 if result.get("ok") else 404)


@mcp_api.get("/tools")
def tools():
    reg = get_mcp_registry()
    return jsonify({"ok": True, "tools": reg.tools()})


@mcp_api.post("/tools/invoke")
def invoke_tool():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    args = dict(data.get("arguments") or {})
    result = get_mcp_registry().invoke_tool(name, args)
    return jsonify(result), (200 if result.get("ok") else 400)
