from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlencode

import aiohttp

from tool_registry import get_tool_registry
from secrets_store import get_secrets_store
from browser_chat import BrowserChatProvider
from mcp_client import MCPClient
from mcp_registry import get_mcp_registry
from task_tool_state import get_task_tool_state_store

_browser = None

CATEGORY_HINTS = {
    "wetter": "wetter",
    "weather": "wetter",
    "suche": "suche",
    "search": "suche",
    "internet": "suche",
    "recherche": "suche",
    "browser": "suche",
    "web": "suche",
    "code": "code",
    "python": "code",
    "github": "code",
    "api": "integration",
    "tool": "integration",
    "mcp": "integration",
    "resource": "resource",
    "datei": "resource",
}


MCP_BRIDGE_URL = os.getenv("MCP_BRIDGE_URL", "http://127.0.0.1:8766")


def infer_category(prompt: str) -> str:
    p = (prompt or '').lower()
    for key, cat in CATEGORY_HINTS.items():
        if key in p:
            return cat
    return "general"


def select_tool_for_prompt(prompt: str, preferred_kind: str = ""):
    reg = get_tool_registry()
    cat = infer_category(prompt)
    return reg.pick(category=cat, kind=preferred_kind) or reg.pick(category=cat) or reg.pick(category="general")


def _headers(tool: dict) -> dict:
    if tool.get("auth_type") != "header":
        return {}
    secret = get_secrets_store().get_secret(tool.get("secret_ref", ""))
    if not secret:
        return {}
    return {tool.get("auth_field") or "Authorization": f'{tool.get("auth_prefix","")}{secret}'}


def _url_with_query_auth(url: str, tool: dict) -> str:
    if tool.get("auth_type") != "query":
        return url
    secret = get_secrets_store().get_secret(tool.get("secret_ref", ""))
    if not secret:
        return url
    joiner = "&" if "?" in url else "?"
    field = tool.get("auth_field") or "api_key"
    return f"{url}{joiner}{urlencode({field: secret})}"


def _append_query(url: str, query_param: str, prompt: str) -> str:
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}{urlencode({query_param or 'q': prompt})}"


def _response_to_text(content_type: str, text: str) -> str:
    if 'application/json' in (content_type or '').lower():
        try:
            data = json.loads(text)
            return json.dumps(data, ensure_ascii=False, indent=2)[:3000]
        except Exception:
            return text[:3000]
    return text[:3000]


async def _run_script(script_path: str, prompt: str) -> tuple[bool, str, int]:
    proc = await asyncio.create_subprocess_exec(
        script_path,
        prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return False, 'Timeout (20s)', -1
    output = (stdout.decode(errors='replace') or stderr.decode(errors='replace') or '').strip()
    return proc.returncode == 0, output[:3000], proc.returncode


async def _run_registry_tool(tool, prompt: str) -> dict:
    reg = get_tool_registry()
    if not tool:
        return {"ok": False, "error": "Kein Tool verfügbar"}
    row = next((x for x in reg.list_tools() if x["tool_id"] == tool.tool_id), None) or {}

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        if tool.kind in ("api", "mcp"):
            if tool.kind == "mcp":
                client = MCPClient(tool.base_url or MCP_BRIDGE_URL)
                features = await discover_mcp_bridge(client)
                tools = features.get("tools") or []
                if tools:
                    best = tools[0]
                    result = await client.invoke_tool(best.get("name", ""), {"prompt": prompt, "query": prompt})
                    ok = bool(result.get("ok"))
                    reg.record(tool.tool_id, ok, f"mcp-run:{result.get('status_code', 200)}")
                    return {
                        "ok": ok,
                        "content": _response_to_text("application/json", json.dumps(result, ensure_ascii=False)),
                        "status_code": result.get("status_code", 200),
                        "via": "mcp",
                        "url": client.api_base,
                    }
            url = (tool.base_url.rstrip("/") + "/" + tool.endpoint.lstrip("/")) if tool.endpoint else tool.base_url
            url = _url_with_query_auth(url, row)
            method = (tool.method or "GET").upper()
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                if method == "POST":
                    async with sess.post(url, headers=_headers(row), json={"prompt": prompt}) as res:
                        text = await res.text()
                        ok = res.status < 400
                        reg.record(tool.tool_id, ok, f"api-run:{res.status}")
                        return {"ok": ok, "content": _response_to_text(res.headers.get('Content-Type', ''), text), "status_code": res.status, "via": "api", "url": str(res.url)}
                else:
                    qurl = _append_query(url, tool.query_param or 'q', prompt)
                    async with sess.get(qurl, headers=_headers(row)) as res:
                        text = await res.text()
                        ok = res.status < 400
                        reg.record(tool.tool_id, ok, f"api-run:{res.status}")
                        return {"ok": ok, "content": _response_to_text(res.headers.get('Content-Type', ''), text), "status_code": res.status, "via": "api", "url": str(res.url)}

        if tool.kind == "search":
            base = tool.base_url or tool.website_url
            url = _url_with_query_auth(base, row)
            qurl = _append_query(url, tool.query_param or 'q', prompt)
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.get(qurl, headers=_headers(row)) as res:
                    text = await res.text()
                    ok = res.status < 400
                    reg.record(tool.tool_id, ok, f"search-run:{res.status}")
                    return {"ok": ok, "content": _response_to_text(res.headers.get('Content-Type', ''), text), "status_code": res.status, "via": "search", "url": str(res.url)}

        if tool.kind == "script":
            ok, content, code = await _run_script(tool.script_path, prompt)
            reg.record(tool.tool_id, ok, f"script-run:{code}")
            return {"ok": ok, "content": content, "via": "script", "status_code": code}

        if tool.kind == "browser_chat":
            global _browser
            if _browser is None:
                _browser = BrowserChatProvider()
            result = await _browser.ask(row, prompt)
            reg.record(tool.tool_id, result.ok, "browser-chat-run")
            return {"ok": result.ok, "content": result.content, "error": result.error, "via": "browser_chat"}

        return {"ok": False, "error": f"Nicht unterstützter Tooltyp: {tool.kind}"}
    except Exception as e:
        reg.record(tool.tool_id, False, f"run-error: {e}")
        return {"ok": False, "error": str(e), "via": getattr(tool, 'kind', 'unknown')}


async def discover_mcp_bridge(client: MCPClient | None = None) -> dict:
    client = client or MCPClient(MCP_BRIDGE_URL)
    try:
        capabilities = await client.capabilities()
        tools = await client.tools()
        resources = await client.resources()
        prompts = await client.prompts()
        return {
            "ok": True,
            "source": "remote",
            "capabilities": capabilities.get("capabilities", capabilities),
            "tools": tools.get("tools", []),
            "resources": resources.get("resources", []),
            "prompts": prompts.get("prompts", []),
            "url": client.api_base,
        }
    except Exception as e:
        reg = get_mcp_registry()
        return {
            "ok": False,
            "source": "local-fallback",
            "error": str(e),
            "capabilities": reg.capabilities(),
            "tools": reg.tools(),
            "resources": reg.resources(),
            "prompts": reg.prompts(),
            "url": client.api_base,
        }


async def list_live_tool_interfaces() -> dict:
    registry_tools = get_tool_registry().list_tools()
    mcp = await discover_mcp_bridge()
    return {
        "registry_tools": registry_tools,
        "mcp": mcp,
        "http_endpoints": [
            {"path": "/api/tools", "method": "GET"},
            {"path": "/api/tools/catalog", "method": "GET"},
            {"path": "/api/tools/live", "method": "GET"},
            {"path": "/api/tools/install_local", "method": "POST"},
            {"path": "/api/tools/add", "method": "POST"},
            {"path": "/api/tools/update", "method": "POST"},
            {"path": "/api/tools/toggle", "method": "POST"},
            {"path": "/api/tools/delete", "method": "POST"},
            {"path": "/api/tools/suggest", "method": "POST"},
            {"path": "/api/mcp/capabilities", "method": "GET"},
            {"path": "/api/mcp/tools", "method": "GET"},
            {"path": "/api/mcp/resources", "method": "GET"},
            {"path": "/api/mcp/prompts", "method": "GET"},
        ],
    }


async def select_live_tool_for_task(task, prompt: str, iteration: int) -> dict | None:
    store = get_task_tool_state_store()
    state = store.get_or_create(task.id, task.prompt)
    reg = get_tool_registry()
    category_pref = state.preferred_categories or [infer_category(prompt)]
    kind_pref = state.preferred_kinds or ["mcp", "api", "search"]

    candidates: list[tuple[float, dict]] = []
    for row in reg.list_tools(active_only=True):
        identifier = row.get("tool_id")
        if identifier in state.used_tool_ids:
            continue
        score = float(row.get("trust", 50.0)) + float(row.get("priority", 50)) / 2
        if row.get("category") in category_pref:
            score += 20
        if row.get("kind") in kind_pref:
            score += 15
        if iteration == 0 and row.get("kind") == "mcp":
            score += 10
        candidates.append((score, {
            "source": "registry",
            "identifier": identifier,
            "name": row.get("name", identifier),
            "kind": row.get("kind", ""),
            "category": row.get("category", "general"),
            "tool": reg.get(identifier),
        }))

    mcp = await discover_mcp_bridge()
    for tool in mcp.get("tools", []):
        identifier = f"mcp:{tool.get('name','')}"
        if identifier in state.used_tool_ids:
            continue
        score = 70.0
        desc = f"{tool.get('description','')} {tool.get('name','')}".lower()
        if any(cat in desc for cat in category_pref):
            score += 10
        score += 12 if mcp.get("source") == "remote" else 6
        candidates.append((score, {
            "source": "mcp_remote" if mcp.get("source") == "remote" else "mcp_local",
            "identifier": identifier,
            "name": tool.get("name", identifier),
            "kind": "mcp",
            "category": category_pref[0],
            "mcp_feature": "tool",
            "mcp_name": tool.get("name", ""),
            "mcp_url": mcp.get("url", MCP_BRIDGE_URL),
        }))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    selected = candidates[0][1]
    store.set_selected(task.id, selected["source"], selected["identifier"], selected["name"])
    return selected


async def run_selected_tool(selection: dict, prompt: str) -> dict:
    if not selection:
        return {"ok": False, "error": "Keine Tool-Auswahl"}
    source = selection.get("source")
    if source == "registry":
        return await _run_registry_tool(selection.get("tool"), prompt)
    if source in ("mcp_remote", "mcp_local"):
        if source == "mcp_local":
            result = get_mcp_registry().invoke_tool(selection.get("mcp_name", ""), {"prompt": prompt, "query": prompt})
            return {"ok": bool(result.get("ok")), "content": json.dumps(result, ensure_ascii=False, indent=2)[:3000], "via": "mcp_local", "status_code": 200 if result.get("ok") else 400}
        client = MCPClient(selection.get("mcp_url") or MCP_BRIDGE_URL)
        result = await client.invoke_tool(selection.get("mcp_name", ""), {"prompt": prompt, "query": prompt})
        return {"ok": bool(result.get("ok")), "content": json.dumps(result, ensure_ascii=False, indent=2)[:3000], "via": "mcp_remote", "status_code": result.get("status_code", 200)}
    return {"ok": False, "error": f"Unbekannte Tool-Quelle: {source}"}


async def run_tool(tool, prompt: str) -> dict:
    return await _run_registry_tool(tool, prompt)
