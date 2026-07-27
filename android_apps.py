"""Isaac – generic Android app control (Magisk/Termux bridge).

List/search packages, launch by fuzzy name, force-stop, UI dump/tap/type,
current activity. Owner/admin only for invasive ops.
"""

from __future__ import annotations

import logging
import re
import shlex
import time
from typing import Any, Optional

from audit import AuditLog
from config import is_owner_equivalent_mode

log = logging.getLogger("Isaac.AndroidApps")

# Extended aliases beyond owner_action._APP_PACKAGES (merged at resolve time)
_EXTRA_ALIASES: dict[str, str] = {
    "whatsapp": "com.whatsapp",
    "n26": "de.number26.android",
    "check24": "de.check24.check24",
    "c24": "de.c24.bankapp",
    "chatgpt": "com.openai.chatgpt",
    "openai": "com.openai.chatgpt",
    "mistral": "ai.mistral.chat",
    "github": "com.github.android",
    "fdroid": "org.fdroid.fdroid",
    "tor": "org.torproject.torbrowser_alpha",
    "kagi": "com.kagi.search",
    "gdocs": "com.google.android.apps.docs",
    "drive": "com.google.android.apps.docs",
    "files": "com.google.android.apps.nbu.files",
    "verivox": "de.verivox.contractmanager",
    "lidl": "de.lidlconnect.android",
}

_pkg_cache: list[str] = []
_pkg_cache_at: float = 0.0


def _owner_ok() -> Optional[str]:
    if is_owner_equivalent_mode():
        return None
    return "Android-App-Steuerung nur im Admin-Modus."


async def _root_sh(cmd: str, *, timeout: float = 45.0) -> dict[str, Any]:
    from chrome_tabs import _root_sh as root_sh

    return await root_sh(cmd, timeout=timeout)


async def _bridge_sh(cmd: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """Non-root shell on Android side (am/input often work without su)."""
    from termux_bridge import bridge_available, run_termux_command

    if not bridge_available():
        return {"ok": False, "error": "Termux-Brücke nicht verfügbar", "stdout": ""}
    return await run_termux_command(["sh", "-c", cmd], timeout=timeout)


async def list_packages(*, third_party_only: bool = False, refresh: bool = False) -> dict[str, Any]:
    blocked = _owner_ok()
    if blocked:
        return {"ok": False, "error": blocked, "packages": []}

    global _pkg_cache, _pkg_cache_at
    if not refresh and _pkg_cache and (time.time() - _pkg_cache_at) < 120:
        pkgs = _pkg_cache
    else:
        flag = "-3" if third_party_only else ""
        # prefer root pm (full access)
        r = await _root_sh(f"pm list packages {flag} 2>/dev/null", timeout=40.0)
        out = r.get("stdout") or ""
        if not out.strip():
            r = await _bridge_sh(f"pm list packages {flag} 2>/dev/null", timeout=40.0)
            out = r.get("stdout") or ""
        pkgs = []
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                pkgs.append(line.split("package:", 1)[1].strip())
        pkgs = sorted(set(pkgs))
        if pkgs:
            _pkg_cache = pkgs
            _pkg_cache_at = time.time()

    return {
        "ok": bool(pkgs),
        "packages": pkgs,
        "count": len(pkgs),
        "third_party_only": third_party_only,
        "error": None if pkgs else "Keine Packages gelesen",
    }


def search_packages(packages: list[str], query: str, *, limit: int = 40) -> list[str]:
    q = (query or "").strip().lower()
    if not q:
        return packages[:limit]
    # alias hit
    alias_pkg = _EXTRA_ALIASES.get(q)
    scored: list[tuple[int, str]] = []
    for p in packages:
        pl = p.lower()
        short = pl.split(".")[-1]
        score = 0
        if pl == q or short == q:
            score = 100
        elif q in pl:
            score = 50 + (10 if short.startswith(q) else 0)
        elif all(part in pl for part in re.split(r"[\s_\-]+", q) if part):
            score = 30
        if score:
            scored.append((score, p))
    if alias_pkg and alias_pkg in packages:
        scored.append((120, alias_pkg))
    scored.sort(key=lambda x: (-x[0], x[1]))
    # dedupe
    seen: set[str] = set()
    out: list[str] = []
    for _, p in scored:
        if p not in seen:
            seen.add(p)
            out.append(p)
        if len(out) >= limit:
            break
    return out


async def resolve_package(name: str) -> dict[str, Any]:
    """Resolve human name or package id to a package."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "kein Name"}

    # static maps
    try:
        from owner_action import _APP_PACKAGES

        static = dict(_APP_PACKAGES)
    except Exception:
        static = {}
    static.update(_EXTRA_ALIASES)

    key = name.lower()
    if key in static:
        return {"ok": True, "package": static[key], "via": "alias", "query": name}
    if re.match(r"^[\w.]+$", name) and name.count(".") >= 1:
        return {"ok": True, "package": name, "via": "raw", "query": name}

    listed = await list_packages(third_party_only=False)
    pkgs = listed.get("packages") or []
    hits = search_packages(pkgs, name, limit=10)
    if not hits:
        # try third-party only listing if full failed
        if not pkgs:
            listed = await list_packages(third_party_only=True, refresh=True)
            pkgs = listed.get("packages") or []
            hits = search_packages(pkgs, name, limit=10)
    if not hits:
        return {
            "ok": False,
            "error": f"Keine App für '{name}' gefunden",
            "query": name,
            "suggestions": [],
        }
    return {
        "ok": True,
        "package": hits[0],
        "via": "search",
        "query": name,
        "suggestions": hits[:8],
    }


async def force_stop(package: str) -> dict[str, Any]:
    blocked = _owner_ok()
    if blocked:
        return {"ok": False, "error": blocked}
    package = (package or "").strip()
    if not re.match(r"^[\w.]+$", package):
        return {"ok": False, "error": "ungültiges package"}
    r = await _root_sh(f"am force-stop {shlex.quote(package)}", timeout=20.0)
    ok = bool(r.get("ok")) or "Error" not in (r.get("stdout") or r.get("stderr") or "")
    AuditLog.action("AndroidApps", "force_stop", package, erfolg=ok)
    return {"ok": ok, "package": package, "detail": (r.get("stdout") or r.get("error") or "")[:200]}


async def current_activity() -> dict[str, Any]:
    r = await _root_sh(
        'dumpsys window 2>/dev/null | grep -E "mCurrentFocus|mFocusedApp" | head -n 6',
        timeout=20.0,
    )
    out = r.get("stdout") or ""
    focus = ""
    m = re.search(r"([a-zA-Z0-9_.]+)/([a-zA-Z0-9_.$]+)", out)
    if m:
        focus = f"{m.group(1)}/{m.group(2)}"
    return {"ok": bool(out.strip()), "focus": focus, "raw": out[:500]}


async def ui_dump_text(*, max_chars: int = 12000) -> dict[str, Any]:
    blocked = _owner_ok()
    if blocked:
        return {"ok": False, "error": blocked}
    r = await _root_sh(
        "uiautomator dump /data/local/tmp/isaac_ui.xml >/dev/null 2>&1; "
        "cat /data/local/tmp/isaac_ui.xml 2>/dev/null",
        timeout=40.0,
    )
    xml = r.get("stdout") or ""
    if not xml.strip().startswith("<?xml") and "<hierarchy" not in xml[:200]:
        return {"ok": False, "error": (r.get("error") or "ui dump leer")[:200], "xml": ""}
    # compact node list for chat
    from ui_automation import parse_ui_xml

    try:
        nodes = parse_ui_xml(xml)
    except Exception as exc:
        return {"ok": False, "error": f"parse: {exc}", "xml": xml[:500]}
    labels = []
    for n in nodes:
        lab = n.label
        if not lab:
            continue
        if len(lab) > 80:
            lab = lab[:77] + "..."
        labels.append(
            {
                "text": lab,
                "clickable": n.clickable,
                "password": n.is_password,
                "center": n.center(),
                "id": (n.resource_id or "")[-40:],
            }
        )
    # dedupe labels
    seen: set[str] = set()
    unique = []
    for row in labels:
        k = row["text"]
        if k in seen:
            continue
        seen.add(k)
        unique.append(row)
    AuditLog.action("AndroidApps", "ui_dump", f"nodes={len(nodes)}", erfolg=True)
    return {
        "ok": True,
        "node_count": len(nodes),
        "labels": unique[:80],
        "xml_len": len(xml),
        "xml_preview": xml[: min(max_chars, 1500)],
    }


async def input_tap(x: int, y: int) -> dict[str, Any]:
    r = await _root_sh(f"input tap {int(x)} {int(y)}", timeout=15.0)
    ok = bool(r.get("ok"))
    return {"ok": ok, "x": x, "y": y, "error": r.get("error")}


async def input_text(text: str) -> dict[str, Any]:
    # input text escapes spaces as %s
    escaped = (text or "").replace(" ", "%s").replace("'", "")
    r = await _root_sh(f"input text {shlex.quote(escaped)}", timeout=20.0)
    return {"ok": bool(r.get("ok")), "len": len(text or ""), "error": r.get("error")}


async def input_key(key: str | int) -> dict[str, Any]:
    from ui_automation import _ANDROID_KEY_ALIASES

    if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
        code = int(key)
    else:
        code = _ANDROID_KEY_ALIASES.get(str(key).lower().strip())
        if code is None:
            return {"ok": False, "error": f"unbekannter key: {key}"}
    r = await _root_sh(f"input keyevent {int(code)}", timeout=15.0)
    return {"ok": bool(r.get("ok")), "key": key, "code": code, "error": r.get("error")}


async def input_swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> dict[str, Any]:
    r = await _root_sh(
        f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration_ms)}",
        timeout=20.0,
    )
    return {"ok": bool(r.get("ok")), "error": r.get("error")}


async def ui_tap_label(label: str) -> dict[str, Any]:
    dump = await ui_dump_text()
    if not dump.get("ok"):
        return dump
    from ui_automation import parse_ui_xml, find_nodes

    # need full xml — re-dump
    r = await _root_sh(
        "cat /data/local/tmp/isaac_ui.xml 2>/dev/null",
        timeout=20.0,
    )
    xml = r.get("stdout") or ""
    if not xml:
        return {"ok": False, "error": "kein UI-XML"}
    nodes = parse_ui_xml(xml)
    hits = find_nodes(nodes, label, clickable_only=False)
    if not hits:
        return {"ok": False, "error": f"Label nicht gefunden: {label}", "labels": [
            x["text"] for x in (dump.get("labels") or [])[:20]
        ]}
    node = hits[0]
    x, y = node.center()
    tapped = await input_tap(x, y)
    AuditLog.action("AndroidApps", "ui_tap", f"{label[:40]} @{x},{y}", erfolg=bool(tapped.get("ok")))
    return {
        "ok": bool(tapped.get("ok")),
        "label": node.label,
        "x": x,
        "y": y,
        "error": tapped.get("error"),
    }


def format_apps_list(result: dict[str, Any], *, query: str = "") -> str:
    if not result.get("ok") and not result.get("packages"):
        return f"[Apps] {result.get('error', 'Fehler')}"
    pkgs = result.get("packages") or []
    if query:
        pkgs = search_packages(pkgs, query, limit=50)
        header = f"[Apps] Suche '{query}': {len(pkgs)} Treffer"
    else:
        pkgs = pkgs[:80]
        header = f"[Apps] {result.get('count', len(pkgs))} Packages (zeige {len(pkgs)})"
    lines = [header, ""]
    for p in pkgs:
        lines.append(f"  {p}")
    lines.append("")
    lines.append("Öffnen: öffne app <name|package> | stop app <package>")
    return "\n".join(lines)


def format_ui_dump(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"[UI] {result.get('error', 'Fehler')}"
    lines = [
        f"[UI] {result.get('node_count', 0)} Nodes, "
        f"{len(result.get('labels') or [])} Labels",
        "",
    ]
    for row in (result.get("labels") or [])[:40]:
        flags = []
        if row.get("clickable"):
            flags.append("tap")
        if row.get("password"):
            flags.append("pwd")
        fl = f" ({','.join(flags)})" if flags else ""
        cx, cy = row.get("center") or (0, 0)
        lines.append(f"  · {row.get('text')}{fl} @{cx},{cy}")
    lines.append("")
    lines.append("Tippen: tippe <text> | tippe xy 100 200 | text hello | key back")
    return "\n".join(lines)
