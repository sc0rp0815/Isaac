from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlencode

import aiohttp

from config import get_config
from tool_registry import get_tool_registry
from secrets_store import get_secrets_store
from browser_chat import BrowserChatProvider
from mcp_client import MCPClient
from mcp_registry import get_mcp_registry
from task_tool_state import get_task_tool_state_store
from tool_policy import ToolDecisionReason, ToolPolicy, ToolSelectionDecision
from result_contract import ensure_result_contract, error_result

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
MCP_SOURCE = "mcp"
_LEGACY_MCP_SOURCES = frozenset({MCP_SOURCE, "mcp_remote", "mcp_local"})


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
    headers = {
        "User-Agent": "Isaac/1.0 (+local tool runtime)",
        "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
    }
    if tool.get("auth_type") != "header":
        return headers
    secret = get_secrets_store().get_secret(tool.get("secret_ref", ""))
    if not secret:
        return headers
    headers[tool.get("auth_field") or "Authorization"] = f'{tool.get("auth_prefix","")}{secret}'
    return headers


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


def _normalize_mcp_url(url: str | None = None) -> str:
    raw = (url or MCP_BRIDGE_URL).strip().rstrip("/")
    if raw.endswith("/api/mcp"):
        return raw[: -len("/api/mcp")]
    return raw


def resolve_mcp_tool_name(
    prompt: str,
    tools: list[dict],
    *,
    preferred_name: str = "",
) -> str:
    preferred = (preferred_name or "").strip()
    if preferred:
        return preferred
    names = [str(tool.get("name", "")).strip() for tool in tools if tool.get("name")]
    if not names:
        return ""
    prompt_l = (prompt or "").lower()
    for marker, tool_name in (
        ("wetter", "isaac.search_web"),
        ("weather", "isaac.search_web"),
        ("suche", "isaac.search_web"),
        ("search", "isaac.search_web"),
        ("browser", "isaac.run_browser_action"),
        ("status", "isaac.task_status"),
        ("audit", "isaac.audit_recent"),
    ):
        if marker in prompt_l and tool_name in names:
            return tool_name
    for name in names:
        if name == "isaac.query_memory":
            return name
    return names[0]


def _mcp_prompt_arguments(prompt: str, extra: dict | None = None) -> dict:
    args = {"prompt": prompt, "query": prompt}
    if extra:
        args.update(extra)
    return args


async def invoke_mcp_tool(
    name: str,
    arguments: dict | None = None,
    *,
    mcp_url: str | None = None,
    bridge: dict | None = None,
) -> dict:
    """Einheitlicher MCP-Tool-Pfad: Remote-Bridge zuerst, lokale Registry als Fallback."""
    tool_name = (name or "").strip()
    if not tool_name:
        return error_result("MCP-Tool-Name fehlt", metadata={"source": MCP_SOURCE})

    args = dict(arguments or {})
    base_url = _normalize_mcp_url(mcp_url)
    client: MCPClient | None = None
    try:
        if bridge is None:
            client = MCPClient(base_url)
            bridge = await discover_mcp_bridge(client)

        if bridge.get("source") == "remote":
            client = client or MCPClient(bridge.get("url") or base_url)
            result = await client.invoke_tool(tool_name, args)
            if result.get("ok"):
                contracted = ensure_result_contract(result, source=MCP_SOURCE)
                contracted["via"] = MCP_SOURCE
                contracted["transport"] = result.get("transport", "jsonrpc")
                contracted["url"] = getattr(client, "api_base", base_url)
                return contracted

        local = get_mcp_registry().invoke_tool(tool_name, args)
        contracted = ensure_result_contract(local, source=MCP_SOURCE)
        contracted["via"] = MCP_SOURCE
        contracted["transport"] = "local"
        contracted["url"] = base_url
        return contracted
    except Exception as exc:
        return error_result(str(exc), metadata={"source": MCP_SOURCE, "tool": tool_name})
    finally:
        if client is not None:
            await client.close()


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
                bridge = await discover_mcp_bridge(MCPClient(_normalize_mcp_url(tool.base_url)))
                mcp_name = resolve_mcp_tool_name(
                    prompt,
                    bridge.get("tools") or [],
                    preferred_name=str((tool.metadata or {}).get("mcp_tool_name", "")),
                )
                if not mcp_name:
                    return {"ok": False, "error": "Kein MCP-Tool verfügbar", "via": MCP_SOURCE}
                result = await invoke_mcp_tool(
                    mcp_name,
                    _mcp_prompt_arguments(prompt),
                    mcp_url=bridge.get("url") or tool.base_url or MCP_BRIDGE_URL,
                    bridge=bridge,
                )
                ok = bool(result.get("ok"))
                reg.record(tool.tool_id, ok, f"mcp-run:{result.get('status_code', 200)}")
                return result
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
            if not get_config().browser_automation:
                return {"ok": False, "error": "Browser-Modelle sind durch Runtime-Policy deaktiviert", "via": "browser_chat"}
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
            "transport": getattr(client, "transport", "rest"),
            "capabilities": capabilities.get("capabilities", capabilities),
            "tools": tools.get("tools", []),
            "resources": resources.get("resources", []),
            "prompts": prompts.get("prompts", []),
            "url": client.api_base,
            "jsonrpc_url": getattr(client, "jsonrpc_url", ""),
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
            {"path": "/api/tools/bundles", "method": "GET"},
            {"path": "/api/tools/live", "method": "GET"},
            {"path": "/api/tools/install_local", "method": "POST"},
            {"path": "/api/tools/install_free_pack", "method": "POST"},
            {"path": "/api/tools/install_bundle", "method": "POST"},
            {"path": "/api/tools/add", "method": "POST"},
            {"path": "/api/tools/update", "method": "POST"},
            {"path": "/api/tools/toggle", "method": "POST"},
            {"path": "/api/tools/delete", "method": "POST"},
            {"path": "/api/tools/suggest", "method": "POST"},
            {"path": "/api/mcp/capabilities", "method": "GET"},
            {"path": "/api/mcp/jsonrpc", "method": "POST"},
            {"path": "/api/mcp/tools", "method": "GET"},
            {"path": "/api/mcp/resources", "method": "GET"},
            {"path": "/api/mcp/prompts", "method": "GET"},
        ],
    }


def _procedure_hints_for_prompt(prompt: str) -> dict[str, float]:
    """Bounded Procedure→Selection: Reliability + leichte Keyword-Überlappung.

    Inspiriert von lokalen Memory-Systemen (z. B. Letta-Blocks / Mem0-Retrieval),
    aber ohne neuen Layer: nutzt nur vorhandene Procedure-Memory-Signaturen.
    """
    try:
        from memory import get_memory
        from procedure_memory import owner_procedure_hints_for_prompt, _extract_keywords

        hints: dict[str, float] = {}
        prompt_terms = set(_extract_keywords(prompt, limit=8))
        for proc in get_memory().search_procedures(prompt, limit=6):
            if proc.get("degraded"):
                continue
            rel = float(proc.get("reliability") or 0.0)
            if rel < 0.45:
                continue
            boost = min(18.0, rel * 12.0)
            # Keyword-Overlap: etwas höhere Priorität bei thematischer Nähe
            proc_terms = {
                str(k).lower()
                for k in (proc.get("keywords") or [])
                if k
            }
            if prompt_terms and proc_terms:
                overlap = len(prompt_terms & proc_terms) / max(1, len(prompt_terms))
                boost += min(6.0, overlap * 8.0)
            for tool_name in proc.get("tools_used") or []:
                name = str(tool_name).strip().lower()
                if name.startswith("owner:"):
                    continue
                if name:
                    hints[name] = max(hints.get(name, 0.0), boost)
        owner_hints, _category = owner_procedure_hints_for_prompt(prompt)
        for name, boost in owner_hints.items():
            hints[name] = max(hints.get(name, 0.0), boost)
        return hints
    except Exception:
        return {}


def _procedure_category_hint_for_prompt(prompt: str) -> str:
    try:
        from procedure_memory import owner_procedure_hints_for_prompt

        _hints, category = owner_procedure_hints_for_prompt(prompt)
        return category
    except Exception:
        return ""


async def select_live_tool_for_task(task, prompt: str, iteration: int, policy: ToolPolicy | None = None) -> ToolSelectionDecision:
    del policy
    store = get_task_tool_state_store()
    state = store.get_or_create(task.id, task.prompt)
    reg = get_tool_registry()
    category_pref = state.preferred_categories or [infer_category(prompt)]
    kind_pref = state.preferred_kinds or ["mcp", "api", "search"]
    procedure_hints = _procedure_hints_for_prompt(prompt)
    owner_category = _procedure_category_hint_for_prompt(prompt)
    if owner_category and owner_category not in category_pref:
        category_pref = [owner_category] + list(category_pref)

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
        hint_key = str(row.get("name", identifier)).lower()
        score += procedure_hints.get(hint_key, 0.0)
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
        mcp_name = str(tool.get("name", "")).lower()
        score += procedure_hints.get(mcp_name, 0.0)
        if mcp_name.startswith("isaac."):
            score += procedure_hints.get(mcp_name.split(".", 1)[-1], 0.0)
        candidates.append((score, {
            "source": MCP_SOURCE,
            "identifier": identifier,
            "name": tool.get("name", identifier),
            "kind": "mcp",
            "category": category_pref[0],
            "mcp_feature": "tool",
            "mcp_name": tool.get("name", ""),
            "mcp_url": mcp.get("url", MCP_BRIDGE_URL),
            "mcp_transport": "remote" if mcp.get("source") == "remote" else "local",
        }))

    if not candidates:
        return ToolSelectionDecision(
            selected=None,
            reason=ToolDecisionReason.ELIGIBLE_BUT_NO_CANDIDATE,
            metadata={
                "candidate_count": 0,
                "category_pref": list(category_pref),
                "kind_pref": list(kind_pref),
                "iteration": iteration,
            },
        )
    candidates.sort(key=lambda x: x[0], reverse=True)
    top_score = candidates[0][0]
    selected = candidates[0][1]
    store.set_selected(task.id, selected["source"], selected["identifier"], selected["name"])
    return ToolSelectionDecision(
        selected=selected,
        reason=ToolDecisionReason.SELECTED_CANDIDATE,
        metadata={
            "candidate_count": len(candidates),
            "selected_score": round(float(top_score), 3),
            "category_pref": list(category_pref),
            "kind_pref": list(kind_pref),
            "iteration": iteration,
            "procedure_hints": len(procedure_hints),
        },
    )


def constitution_gate_for_tool(
    selection: dict,
    prompt: str,
    override_ctx=None,
) -> dict | None:
    """Prüft kritische Tool-Aufrufe gegen die Verfassung (mit optionalem Owner-Override)."""
    from constitution_override import apply_constitution_gate

    selection = selection or {}
    kind = str(selection.get("kind", "")).lower()
    name = str(selection.get("name") or selection.get("identifier") or "").lower()
    mcp_name = str(selection.get("mcp_name", "")).lower()
    prompt_l = (prompt or "").lower()
    shell_like = (
        kind in {"code", "shell"}
        or "shell" in name
        or "run_shell" in name
        or "run_shell" in mcp_name
        or mcp_name.endswith(".run_shell")
    )
    metadata: dict = {
        "outside_effect": True,
        "audit_logged": True,
        "risk": "high" if kind in {"code", "integration", "shell"} or shell_like else "normal",
    }
    if shell_like:
        # Destruktive Shell-Muster aus dem Prompt/Tool-Namen erkennen.
        destructive_tokens = (
            "rm -rf", "sudo ", "mkfs", "dd if=", "chmod 777", "| bash", "| sh",
            "curl ", "wget ",
        )
        metadata["destructive"] = any(tok in prompt_l for tok in destructive_tokens)
        try:
            from config import is_owner_equivalent_mode
            metadata["owner_approved"] = bool(is_owner_equivalent_mode())
        except Exception:
            metadata["owner_approved"] = False
    if "constitution" in mcp_name and any(
        token in prompt_l for token in ("änder", "umschreib", "modify", "rewrite")
    ):
        metadata["self_modify_constitution"] = True

    action = "system_command" if shell_like else "tool_invoke"
    gate = apply_constitution_gate(action, metadata, override_ctx)
    if gate.get("allowed"):
        return None

    blocked = gate.get("blocked_by", [])
    override = gate.get("override") or {}
    reason = override.get("reason", "Verfassung blockiert")
    return error_result(
        f"Verfassung blockiert Tool-Aufruf: {', '.join(blocked)} ({reason})",
        metadata={
            "blocked_by": blocked,
            "source": "constitution",
            "override_denied": override,
            "action": action,
        },
    )


async def run_selected_tool(
    selection: dict,
    prompt: str,
    override_ctx=None,
    *,
    skip_constitution: bool = False,
) -> dict:
    if not selection:
        return error_result("Keine Tool-Auswahl", metadata={"source": "selection"})
    # Executor prüft Constitution oft bereits selbst — dann nicht doppelt.
    if not skip_constitution:
        blocked = constitution_gate_for_tool(selection, prompt, override_ctx=override_ctx)
        if blocked:
            return blocked
    source = selection.get("source")
    if source == "registry":
        return ensure_result_contract(await _run_registry_tool(selection.get("tool"), prompt), source="registry")
    if source in _LEGACY_MCP_SOURCES:
        extra_args = dict(selection.get("mcp_arguments") or {})
        return await invoke_mcp_tool(
            selection.get("mcp_name", ""),
            _mcp_prompt_arguments(prompt, extra_args),
            mcp_url=selection.get("mcp_url"),
        )
    return error_result(f"Unbekannte Tool-Quelle: {source}", metadata={"source": source or "unknown"})


async def run_tool(tool, prompt: str) -> dict:
    return await _run_registry_tool(tool, prompt)
