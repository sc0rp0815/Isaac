"""Isaac – Security Toolkit (Admin-only)

Katalog, Installation, Update und Ausführung von Security-Tools
(metasploit, aircrack-ng, routersploit, nethunter-helpers, …).
Nur mit ISAAC_PRIVILEGE_MODE=admin.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from audit import AuditLog
from config import BASE_DIR, DATA_DIR, is_owner_equivalent_mode

log = logging.getLogger("Isaac.SecurityToolkit")

STATE_PATH = DATA_DIR / "security_toolkit.json"
CUSTOM_TOOLS_PATH = DATA_DIR / "security_toolkit_custom.json"

_PKG_MANAGER: Optional[str] = None


@dataclass(frozen=True)
class SecurityToolSpec:
    tool_id: str
    display_name: str
    binaries: tuple[str, ...]
    category: str = "security"
    description: str = ""
    apt_packages: tuple[str, ...] = ()
    pkg_packages: tuple[str, ...] = ()
    pip_packages: tuple[str, ...] = ()
    git_repo: str = ""
    git_dir: str = ""
    pip_editable: bool = False
    operations: dict[str, str] = field(default_factory=dict)
    requires_root: bool = False
    nethunter_builtin: bool = False


SECURITY_TOOL_CATALOG: dict[str, SecurityToolSpec] = {
    "metasploit": SecurityToolSpec(
        tool_id="metasploit",
        display_name="Metasploit Framework",
        binaries=("msfconsole", "msfdb"),
        description="Exploit-Framework (msfconsole)",
        apt_packages=("metasploit-framework",),
        pkg_packages=(),
        operations={
            "status": "msfconsole --version 2>/dev/null || msfdb status 2>/dev/null || which msfconsole",
            "console": "msfconsole -q -x 'version; exit'",
        },
        requires_root=False,
        nethunter_builtin=True,
    ),
    "aircrack": SecurityToolSpec(
        tool_id="aircrack",
        display_name="Aircrack-ng",
        binaries=("aircrack-ng", "airodump-ng", "aireplay-ng"),
        description="WLAN-Analyse und Cracking",
        apt_packages=("aircrack-ng",),
        pkg_packages=("aircrack-ng",),
        operations={
            "status": "aircrack-ng --help 2>&1 | head -3",
            "scan": "airodump-ng --help 2>&1 | head -2",
            "interfaces": "iw dev 2>/dev/null || ip link | grep -E 'wlan|wifi'",
        },
        requires_root=True,
        nethunter_builtin=True,
    ),
    "routersploit": SecurityToolSpec(
        tool_id="routersploit",
        display_name="RouterSploit",
        binaries=("rsf.py",),
        description="Router-Exploit-Framework",
        pip_packages=("routersploit",),
        git_repo="https://github.com/threat9/routersploit.git",
        git_dir=str(BASE_DIR / "workspace" / "tools" / "routersploit"),
        operations={
            "status": "python3 -c \"import routersploit; print('routersploit ok')\" 2>/dev/null",
            "cli": "cd {git_dir} && python3 rsf.py --help 2>&1 | head -5",
        },
    ),
    "nmap": SecurityToolSpec(
        tool_id="nmap",
        display_name="Nmap",
        binaries=("nmap",),
        apt_packages=("nmap",),
        pkg_packages=("nmap",),
        operations={
            "status": "nmap --version 2>/dev/null | head -2",
            "quick_scan": "nmap -F {target}",
            "scan": "nmap -sV {target}",
        },
    ),
    "sqlmap": SecurityToolSpec(
        tool_id="sqlmap",
        display_name="SQLMap",
        binaries=("sqlmap",),
        apt_packages=("sqlmap",),
        pip_packages=("sqlmap",),
        operations={
            "status": "sqlmap --version 2>/dev/null | head -2",
        },
    ),
    "hydra": SecurityToolSpec(
        tool_id="hydra",
        display_name="Hydra",
        binaries=("hydra",),
        apt_packages=("hydra",),
        operations={"status": "hydra -h 2>&1 | head -3"},
    ),
    "wifite": SecurityToolSpec(
        tool_id="wifite",
        display_name="Wifite",
        binaries=("wifite",),
        apt_packages=("wifite",),
        pip_packages=("wifite",),
        operations={"status": "wifite --help 2>&1 | head -3"},
        requires_root=True,
    ),
    "reaver": SecurityToolSpec(
        tool_id="reaver",
        display_name="Reaver",
        binaries=("reaver",),
        apt_packages=("reaver",),
        operations={"status": "reaver -h 2>&1 | head -3"},
        requires_root=True,
    ),
    "bettercap": SecurityToolSpec(
        tool_id="bettercap",
        display_name="Bettercap",
        binaries=("bettercap",),
        apt_packages=("bettercap",),
        operations={"status": "bettercap -version 2>/dev/null || bettercap -h 2>&1 | head -2"},
        requires_root=True,
    ),
    "nethunter": SecurityToolSpec(
        tool_id="nethunter",
        display_name="Kali NetHunter",
        binaries=("nethunter", "kalify-chroot"),
        description="NetHunter/Kali-Chroot Status und Helfer",
        operations={
            "status": "command -v nethunter >/dev/null && nethunter status 2>/dev/null; command -v kalify-chroot >/dev/null && echo kalify-chroot:ok; ls /data/local/nhsystem 2>/dev/null | head -3",
            "chroot": "nethunter 2>/dev/null || echo 'NetHunter CLI nicht gefunden — prüfe Kali-Chroot Installation'",
        },
        nethunter_builtin=True,
    ),
}

_TOOL_ALIASES: dict[str, str] = {
    "msf": "metasploit",
    "msfconsole": "metasploit",
    "metasploit-framework": "metasploit",
    "aircrack-ng": "aircrack",
    "airodump": "aircrack",
    "router sploit": "routersploit",
    "router-sploit": "routersploit",
    "rsf": "routersploit",
    "net hunter": "nethunter",
    "kali": "nethunter",
    "kali-nethunter": "nethunter",
}


def security_toolkit_enabled() -> bool:
    return is_owner_equivalent_mode()


def detect_package_manager() -> str:
    global _PKG_MANAGER
    if _PKG_MANAGER:
        return _PKG_MANAGER
    env = (os.getenv("ISAAC_RUNTIME_ENV") or "").strip().lower()
    if env == "termux" or Path("/data/data/com.termux").exists():
        _PKG_MANAGER = "pkg"
        return _PKG_MANAGER
    if shutil.which("apt-get") or shutil.which("apt"):
        _PKG_MANAGER = "apt"
        return _PKG_MANAGER
    if shutil.which("pkg"):
        _PKG_MANAGER = "pkg"
        return _PKG_MANAGER
    _PKG_MANAGER = "unknown"
    return _PKG_MANAGER


def normalize_tool_id(name: str) -> str:
    raw = (name or "").strip().lower()
    raw = re.sub(r"\s+", " ", raw)
    if raw in _TOOL_ALIASES:
        return _TOOL_ALIASES[raw]
    if raw in SECURITY_TOOL_CATALOG:
        return raw
    for key in SECURITY_TOOL_CATALOG:
        if key in raw or raw in key:
            return key
    return raw.replace(" ", "-")


def list_catalog() -> list[dict[str, Any]]:
    state = _load_state()
    installed = set(state.get("installed") or [])
    rows: list[dict[str, Any]] = []
    for spec in SECURITY_TOOL_CATALOG.values():
        available = _binary_available(spec)
        rows.append({
            "tool_id": spec.tool_id,
            "name": spec.display_name,
            "category": spec.category,
            "description": spec.description,
            "installed": spec.tool_id in installed or available,
            "binary_found": available,
            "requires_root": spec.requires_root,
        })
    for custom in _load_custom_tools():
        rows.append({
            "tool_id": custom.get("tool_id", ""),
            "name": custom.get("display_name", ""),
            "category": "custom",
            "description": custom.get("description", ""),
            "installed": True,
            "binary_found": _command_exists(custom.get("binary", "")),
            "requires_root": bool(custom.get("requires_root", False)),
        })
    return sorted(rows, key=lambda r: r.get("name", "").lower())


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"installed": [], "last_sync": "", "history": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"installed": [], "last_sync": "", "history": []}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_custom_tools() -> list[dict[str, Any]]:
    if not CUSTOM_TOOLS_PATH.exists():
        return []
    try:
        data = json.loads(CUSTOM_TOOLS_PATH.read_text(encoding="utf-8"))
        return list(data.get("tools") or [])
    except Exception:
        return []


def _save_custom_tools(tools: list[dict[str, Any]]) -> None:
    CUSTOM_TOOLS_PATH.write_text(
        json.dumps({"tools": tools, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def register_custom_tool(
    *,
    tool_id: str,
    display_name: str,
    binary: str = "",
    install_command: str = "",
    run_template: str = "",
    description: str = "",
) -> dict[str, Any]:
    if not security_toolkit_enabled():
        return {"ok": False, "error": "Nur im Admin-Modus"}
    tid = normalize_tool_id(tool_id)
    entry = {
        "tool_id": tid,
        "display_name": display_name or tid,
        "binary": binary.strip(),
        "install_command": install_command.strip(),
        "run_template": run_template.strip(),
        "description": description.strip(),
        "added": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    tools = [t for t in _load_custom_tools() if t.get("tool_id") != tid]
    tools.append(entry)
    _save_custom_tools(tools)
    AuditLog.action("SecurityToolkit", "register_custom", f"{tid} {display_name[:60]}")
    return {"ok": True, "tool": entry}


def _command_exists(name: str) -> bool:
    return bool(name and shutil.which(name))


def _binary_available(spec: SecurityToolSpec) -> bool:
    if any(_command_exists(b) for b in spec.binaries):
        return True
    if spec.git_dir and Path(spec.git_dir).exists():
        for binary in spec.binaries:
            if (Path(spec.git_dir) / binary).exists():
                return True
    return False


async def _shell(command: str, timeout: float = 120.0) -> dict[str, Any]:
    from owner_action import _shell as owner_shell

    return await owner_shell(command, timeout=timeout)


def _install_command_for(spec: SecurityToolSpec) -> list[str]:
    pm = detect_package_manager()
    cmds: list[str] = []
    if pm == "apt" and spec.apt_packages:
        pkgs = " ".join(spec.apt_packages)
        cmds.append(f"apt-get update -qq && apt-get install -y {pkgs}")
    elif pm == "pkg" and spec.pkg_packages:
        pkgs = " ".join(spec.pkg_packages)
        cmds.append(f"pkg install -y {pkgs}")
    if spec.pip_packages:
        pkgs = " ".join(spec.pip_packages)
        cmds.append(f"pip install -U {pkgs}")
    if spec.git_repo and spec.git_dir:
        dest = Path(spec.git_dir)
        if dest.exists():
            cmds.append(f"cd {dest} && git pull --ff-only 2>/dev/null || true")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            cmds.append(f"git clone {spec.git_repo} {dest}")
        if spec.pip_editable:
            cmds.append(f"pip install -e {dest}")
    return cmds


async def install_tool(tool_id: str) -> tuple[str, bool]:
    if not security_toolkit_enabled():
        return "[Security] Nur im Admin-Modus verfügbar.", False

    tid = normalize_tool_id(tool_id)
    spec = SECURITY_TOOL_CATALOG.get(tid)
    if not spec:
        custom = next((t for t in _load_custom_tools() if t.get("tool_id") == tid), None)
        if not custom:
            return f"[Security] Unbekanntes Tool: {tool_id}", False
        cmd = custom.get("install_command") or ""
        if not cmd:
            return f"[Security] Kein Install-Befehl für {tid} hinterlegt.", False
        AuditLog.action("SecurityToolkit", "install_custom", tid)
        result = await _shell(cmd, timeout=300.0)
        ok = bool(result.get("ok"))
        return _format_shell_result(f"Install {tid}", cmd, result), ok

    if _binary_available(spec):
        return f"[Security] {spec.display_name} ist bereits verfügbar.", True

    cmds = _install_command_for(spec)
    if not cmds:
        return f"[Security] Keine Installationsmethode für {spec.display_name} auf {detect_package_manager()}.", False

    AuditLog.action("SecurityToolkit", "install", tid)
    lines = [f"[Security] Installiere {spec.display_name}…", ""]
    ok = True
    for cmd in cmds:
        result = await _shell(cmd, timeout=300.0)
        lines.append(_format_shell_result("", cmd, result))
        ok = ok and bool(result.get("ok"))

    state = _load_state()
    installed = list(state.get("installed") or [])
    if tid not in installed:
        installed.append(tid)
    state["installed"] = installed
    state.setdefault("history", []).append({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "action": "install",
        "tool_id": tid,
        "ok": ok,
    })
    state["history"] = state["history"][-50:]
    _save_state(state)
    return "\n".join(lines).strip(), ok


async def update_tool(tool_id: str) -> tuple[str, bool]:
    if not security_toolkit_enabled():
        return "[Security] Nur im Admin-Modus verfügbar.", False

    tid = normalize_tool_id(tool_id)
    spec = SECURITY_TOOL_CATALOG.get(tid)
    if spec:
        pm = detect_package_manager()
        cmds: list[str] = []
        if pm == "apt" and spec.apt_packages:
            cmds.append(f"apt-get update -qq && apt-get install -y --only-upgrade {' '.join(spec.apt_packages)}")
        elif pm == "pkg" and spec.pkg_packages:
            cmds.append(f"pkg upgrade -y {' '.join(spec.pkg_packages)}")
        if spec.pip_packages:
            cmds.append(f"pip install -U {' '.join(spec.pip_packages)}")
        if spec.git_repo and spec.git_dir and Path(spec.git_dir).exists():
            cmds.append(f"cd {spec.git_dir} && git pull --ff-only")
        if not cmds:
            return f"[Security] Kein Update-Pfad für {spec.display_name}.", False
        AuditLog.action("SecurityToolkit", "update", tid)
        lines = [f"[Security] Update {spec.display_name}", ""]
        ok = True
        for cmd in cmds:
            result = await _shell(cmd, timeout=300.0)
            lines.append(_format_shell_result("", cmd, result))
            ok = ok and bool(result.get("ok"))
        return "\n".join(lines).strip(), ok

    custom = next((t for t in _load_custom_tools() if t.get("tool_id") == tid), None)
    if custom and custom.get("install_command"):
        return await install_tool(tid)
    return f"[Security] Unbekanntes Tool: {tool_id}", False


def _format_shell_result(title: str, cmd: str, result: dict[str, Any]) -> str:
    parts: list[str] = []
    if title:
        parts.append(title)
    parts.append(f"$ {cmd}")
    if result.get("stdout"):
        parts.append(str(result["stdout"])[:4000])
    if result.get("stderr"):
        parts.append(f"stderr: {str(result['stderr'])[:800]}")
    if result.get("error"):
        parts.append(f"error: {result['error']}")
    return "\n".join(parts)


async def run_tool(
    tool_id: str,
    operation: str = "status",
    *,
    target: str = "",
    extra: str = "",
) -> tuple[str, bool]:
    if not security_toolkit_enabled():
        return "[Security] Nur im Admin-Modus verfügbar.", False

    tid = normalize_tool_id(tool_id)
    op = (operation or "status").strip().lower()
    spec = SECURITY_TOOL_CATALOG.get(tid)

    if not spec:
        custom = next((t for t in _load_custom_tools() if t.get("tool_id") == tid), None)
        if not custom:
            return f"[Security] Unbekanntes Tool: {tool_id}", False
        template = custom.get("run_template") or (f"{custom.get('binary', '')} {{extra}}" if custom.get("binary") else "")
        if not template:
            return f"[Security] Kein Run-Template für {tid}.", False
        cmd = template.format(target=target or "127.0.0.1", extra=extra or "", op=op)
        AuditLog.action("SecurityToolkit", "run_custom", f"{tid}:{op}")
        result = await _shell(cmd, timeout=180.0)
        return _format_shell_result(f"[Security] {tid} ({op})", cmd, result), bool(result.get("ok"))

    if not _binary_available(spec):
        install_msg, installed = await install_tool(tid)
        if not installed:
            return install_msg + "\n\n[Security] Auto-Install fehlgeschlagen.", False

    template = spec.operations.get(op) or spec.operations.get("status", "")
    if not template:
        return f"[Security] Operation '{op}' für {spec.display_name} nicht definiert.", False

    cmd = template.format(
        target=target or "127.0.0.1",
        extra=extra or "",
        git_dir=spec.git_dir or str(BASE_DIR / "workspace" / "tools" / tid),
    )
    AuditLog.action("SecurityToolkit", "run", f"{tid}:{op} target={target[:40]}")
    result = await _shell(cmd, timeout=180.0)
    lines = _format_shell_result(f"[Security] {spec.display_name} ({op})", cmd, result)
    return lines, bool(result.get("ok"))


async def sync_toolkit(*, install_missing: bool = True) -> tuple[str, bool]:
    if not security_toolkit_enabled():
        return "[Security] Nur im Admin-Modus verfügbar.", False

    AuditLog.action("SecurityToolkit", "sync", f"install_missing={install_missing}")
    lines = ["[Security] Toolkit-Sync", f"Package-Manager: {detect_package_manager()}", ""]
    ok = True
    for spec in SECURITY_TOOL_CATALOG.values():
        available = _binary_available(spec)
        lines.append(f"• {spec.display_name}: {'OK' if available else 'fehlt'}")
        if not available and install_missing:
            msg, installed = await install_tool(spec.tool_id)
            lines.append(msg[:500])
            ok = ok and installed

    state = _load_state()
    state["last_sync"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state.setdefault("history", []).append({
        "ts": state["last_sync"],
        "action": "sync",
        "ok": ok,
    })
    state["history"] = state["history"][-50:]
    _save_state(state)
    return "\n".join(lines).strip(), ok


def parse_security_command(text: str) -> Optional[dict[str, Any]]:
    """Erkennt Security-Toolkit-Befehle in Natursprache."""
    if not security_toolkit_enabled():
        return None

    raw = (text or "").strip()
    normalized = re.sub(r"\s+", " ", raw.lower())
    normalized = re.sub(r"^isaac[,:]\s+", "", normalized)

    m = re.search(
        r"registriere\s+(?:security\s+)?tool\s+([a-z0-9_-]+)(?:\s+(?:mit|install)\s+(.+))?$",
        normalized,
        re.I,
    )
    if m:
        return {
            "action": "register",
            "tool_id": m.group(1).strip(),
            "install_command": (m.group(2) or "").strip(),
            "display_name": m.group(1).strip(),
        }

    from security_workflows import match_workflow

    workflow = match_workflow(raw)
    if workflow:
        return workflow

    if re.search(r"(welche|liste|zeige|show).*(workflow|ablauf)", normalized):
        return {"action": "list_workflows"}

    if re.search(r"(welche|liste|zeige|show).*(security|hacking|pentest|werkzeug|toolkit)", normalized):
        return {"action": "list"}

    if re.search(
        r"(?:sync|synchronisiere).*(?:security\s+)?toolkit|toolkit\s+sync|aktualisiere.*security.*tools",
        normalized,
    ):
        return {"action": "sync", "install_missing": "install" in normalized or "fehlend" in normalized}

    m = re.search(
        r"(?:installiere|update|aktualisiere|erweitere)\s+(?:security\s+)?(?:tool\s+)?(.+)$",
        normalized,
    )
    if m:
        tool = normalize_tool_id(m.group(1).strip(" .,!?"))
        action = "update" if "aktualisiere" in normalized or "update" in normalized else "install"
        return {"action": action, "tool_id": tool}

    m = re.search(
        r"(?:nutze|benutze|starte|führe aus|fuehre aus|scanne mit|scan mit)\s+(.+)$",
        normalized,
    )
    if m:
        tail = m.group(1).strip()
        for alias, tid in sorted(_TOOL_ALIASES.items(), key=lambda x: -len(x[0])):
            if alias in tail:
                tool_id = tid
                break
        else:
            tool_id = normalize_tool_id(tail.split()[0] if tail else "")
        target = ""
        tm = re.search(r"(?:auf|gegen|target|ziel)\s+([^\s]+)", tail)
        if tm:
            target = tm.group(1).strip(" .,!?")
        op = "scan" if "scan" in normalized else "status"
        if "console" in tail:
            op = "console"
        return {"action": "run", "tool_id": tool_id, "operation": op, "target": target}

    for tid, spec in SECURITY_TOOL_CATALOG.items():
        if tid in normalized or spec.display_name.lower() in normalized:
            op = "status"
            if "scan" in normalized:
                op = "scan" if "scan" in (spec.operations or {}) else "status"
            target = ""
            tm = re.search(r"(?:auf|gegen|target)\s+([^\s]+)", normalized)
            if tm:
                target = tm.group(1)
            action = "install" if "install" in normalized else "run"
            if "update" in normalized or "aktualisiere" in normalized:
                action = "update"
            return {"action": action, "tool_id": tid, "operation": op, "target": target}

    return None


async def execute_security_command(parsed: dict[str, Any]) -> tuple[str, bool]:
    action = parsed.get("action", "")
    if action == "workflow":
        from security_workflows import run_workflow

        return await run_workflow(
            str(parsed.get("workflow_id") or ""),
            target=str(parsed.get("target") or ""),
        )
    if action == "list_workflows":
        from security_workflows import list_workflows

        lines = ["[Security] Workflows", ""]
        for row in list_workflows():
            lines.append(f"• {row['workflow_id']}: {row['title']} — {row['description']}")
        return "\n".join(lines), True
    if action == "list":
        rows = list_catalog()
        lines = ["[Security] Toolkit-Katalog", ""]
        for row in rows:
            mark = "✓" if row.get("binary_found") else "○"
            lines.append(f"{mark} {row.get('name')} ({row.get('tool_id')}) — {row.get('description')[:60]}")
        return "\n".join(lines), True
    if action == "sync":
        return await sync_toolkit(install_missing=bool(parsed.get("install_missing", True)))
    if action == "install":
        return await install_tool(str(parsed.get("tool_id") or ""))
    if action == "update":
        return await update_tool(str(parsed.get("tool_id") or ""))
    if action == "run":
        return await run_tool(
            str(parsed.get("tool_id") or ""),
            str(parsed.get("operation") or "status"),
            target=str(parsed.get("target") or ""),
            extra=str(parsed.get("extra") or ""),
        )
    if action == "register":
        out = register_custom_tool(
            tool_id=str(parsed.get("tool_id") or ""),
            display_name=str(parsed.get("display_name") or ""),
            install_command=str(parsed.get("install_command") or ""),
        )
        if out.get("ok"):
            return f"[Security] Tool registriert: {out.get('tool', {}).get('tool_id')}", True
        return f"[Security] {out.get('error', 'Registrierung fehlgeschlagen')}", False
    return "[Security] Unbekannte Aktion.", False