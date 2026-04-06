from __future__ import annotations
import subprocess
from urllib.parse import urlencode
import requests

from tool_registry import get_tool_registry
from secrets_store import get_secrets_store
from browser_chat import BrowserChatProvider

_browser = None

CATEGORY_HINTS = {
    "wetter": "wetter",
    "weather": "wetter",
    "suche": "suche",
    "search": "suche",
    "internet": "suche",
    "recherche": "suche",
    "code": "code",
    "python": "code",
    "github": "code",
}

def infer_category(prompt: str) -> str:
    p = prompt.lower()
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

async def run_tool(tool, prompt: str) -> dict:
    reg = get_tool_registry()
    if not tool:
        return {"ok": False, "error": "Kein Tool verfügbar"}
    row = next((x for x in reg.list_tools() if x["tool_id"] == tool.tool_id), None) or {}

    try:
        if tool.kind == "api":
            url = (tool.base_url.rstrip("/") + "/" + tool.endpoint.lstrip("/")) if tool.endpoint else tool.base_url
            url = _url_with_query_auth(url, row)
            method = (tool.method or "GET").upper()
            if method == "POST":
                res = requests.post(url, headers=_headers(row), json={"prompt": prompt}, timeout=20)
            else:
                qname = tool.query_param or "q"
                joiner = "&" if "?" in url else "?"
                res = requests.get(f"{url}{joiner}{qname}={prompt}", headers=_headers(row), timeout=20)
            ok = res.ok
            reg.record(tool.tool_id, ok, "api-run")
            return {"ok": ok, "content": res.text[:3000], "status_code": res.status_code, "via": "api"}

        if tool.kind == "search":
            base = tool.base_url or tool.website_url
            qname = tool.query_param or "q"
            url = f"{base}{'&' if '?' in base else '?'}{qname}={prompt}"
            url = _url_with_query_auth(url, row)
            res = requests.get(url, headers=_headers(row), timeout=20)
            ok = res.ok
            reg.record(tool.tool_id, ok, "search-run")
            return {"ok": ok, "content": res.text[:3000], "status_code": res.status_code, "via": "search"}

        if tool.kind == "script":
            proc = subprocess.run([tool.script_path, prompt], capture_output=True, text=True, timeout=20)
            ok = proc.returncode == 0
            reg.record(tool.tool_id, ok, "script-run")
            return {"ok": ok, "content": (proc.stdout or proc.stderr)[:3000], "via": "script"}

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
        return {"ok": False, "error": str(e), "via": tool.kind}
