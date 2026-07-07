from __future__ import annotations
from flask import Blueprint, jsonify, request
from tool_registry import get_tool_registry
from secrets_store import get_secrets_store
from tool_runtime import select_tool_for_prompt

dashboard_api = Blueprint("dashboard_api", __name__, url_prefix="/api")
registry = get_tool_registry()
secrets = get_secrets_store()

@dashboard_api.get("/tools")
def list_tools():
    return jsonify({"ok": True, "tools": registry.list_tools()})

@dashboard_api.post("/tools/add")
def add_tool():
    data = request.get_json(silent=True) or {}
    api_key = (data.pop("api_key", "") or "").strip()
    if not data.get("name") or not data.get("kind"):
        return jsonify({"ok": False, "error": "name und kind sind Pflicht"}), 400
    tool = registry.add(data)
    if api_key:
        ref = f"{tool.tool_id}_secret"
        secrets.set_secret(ref, api_key)
        registry.update(tool.tool_id, {"secret_ref": ref})
    row = next(x for x in registry.list_tools() if x["tool_id"] == tool.tool_id)
    return jsonify({"ok": True, "tool": row})

@dashboard_api.post("/tools/update")
def update_tool():
    data = request.get_json(silent=True) or {}
    tool_id = (data.get("tool_id") or "").strip()
    if not tool_id:
        return jsonify({"ok": False, "error": "tool_id fehlt"}), 400
    api_key = (data.pop("api_key", "") or "").strip()
    patch = {k: v for k, v in data.items() if k != "tool_id"}
    tool = registry.update(tool_id, patch)
    if api_key:
        ref = tool.secret_ref or f"{tool.tool_id}_secret"
        secrets.set_secret(ref, api_key)
        registry.update(tool.tool_id, {"secret_ref": ref})
    row = next(x for x in registry.list_tools() if x["tool_id"] == tool.tool_id)
    return jsonify({"ok": True, "tool": row})

@dashboard_api.post("/tools/delete")
def delete_tool():
    data = request.get_json(silent=True) or {}
    return jsonify({"ok": registry.delete((data.get("tool_id") or "").strip())})

@dashboard_api.post("/tools/toggle")
def toggle_tool():
    data = request.get_json(silent=True) or {}
    tool = registry.update((data.get("tool_id") or "").strip(), {"active": bool(data.get("active", True))})
    row = next(x for x in registry.list_tools() if x["tool_id"] == tool.tool_id)
    return jsonify({"ok": True, "tool": row})

@dashboard_api.post("/tools/suggest")
def suggest_tool():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    tool = select_tool_for_prompt(prompt)
    if not tool:
        return jsonify({"ok": False, "error": "Kein passendes Tool"}), 404
    row = next(x for x in registry.list_tools() if x["tool_id"] == tool.tool_id)
    return jsonify({"ok": True, "tool": row})
