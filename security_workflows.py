"""Isaac – Security Workflows & NetHunter-Integration (Admin-only)

Mehrstufige Tool-Workflows und Kali-Chroot-Ausführung.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from audit import AuditLog
from config import BASE_DIR, WORKSPACE, is_owner_equivalent_mode

log = logging.getLogger("Isaac.SecurityWorkflows")

SCAN_DIR = WORKSPACE / "security_scans"
NETHUNTER_CHROOT_CANDIDATES: tuple[str, ...] = (
    "/data/local/nhsystem/kali-arm64",
    "/data/local/nhsystem/kali-armhf",
    "/data/data/com.offsec.nethunter/files/chroot",
    "/data/user/0/com.offsec.nethunter/files/chroot",
    "/data/local/nhsystem/kali",
)

NETHUNTER_BOOTSTRAP_PACKAGES = (
    "metasploit-framework",
    "aircrack-ng",
    "nmap",
    "sqlmap",
    "hydra",
    "wifite",
)


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    command: str
    timeout: float = 90.0
    optional: bool = False


@dataclass(frozen=True)
class SecurityWorkflow:
    workflow_id: str
    title: str
    description: str
    steps: tuple[WorkflowStep, ...]
    requires_root: bool = False


WORKFLOW_REGISTRY: dict[str, SecurityWorkflow] = {
    "wlan_survey": SecurityWorkflow(
        workflow_id="wlan_survey",
        title="WLAN-Umgebung analysieren",
        description="Interfaces, Verbindung, Netze in der Nähe, Gateway",
        steps=(
            WorkflowStep("interfaces", "iw dev 2>/dev/null || ip link show | grep -E 'wlan|wifi'"),
            WorkflowStep("connection", "iwgetid -r 2>/dev/null; iw dev wlan0 link 2>/dev/null; ip -4 addr show wlan0 2>/dev/null"),
            WorkflowStep("scan", "iw dev wlan0 scan 2>/dev/null | grep -E 'SSID|signal|freq' | head -40", optional=True),
            WorkflowStep("gateway", "ip route | awk '/default/ {print \"Gateway:\", $3}'"),
        ),
    ),
    "wlan_wifite_scan": SecurityWorkflow(
        workflow_id="wlan_wifite_scan",
        title="WLAN mit Wifite scannen",
        description="Kurzer Wifite-Recon-Lauf (ohne Crack, Zeitlimit)",
        requires_root=True,
        steps=(
            WorkflowStep("iface", "iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}' || echo wlan0"),
            WorkflowStep("wifite_check", "command -v wifite >/dev/null && wifite --help 2>&1 | head -5"),
            WorkflowStep(
                "wifite_scan",
                "IFACE=$(iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}'); IFACE=${IFACE:-wlan0}; "
                "timeout 40 wifite -i \"$IFACE\" --nodeauths 2>&1 | head -100",
                timeout=120.0,
                optional=True,
            ),
        ),
    ),
    "wlan_aircrack_scan": SecurityWorkflow(
        workflow_id="wlan_aircrack_scan",
        title="WLAN mit Aircrack scannen",
        description="Kurzer airodump-ng Sweep (Monitor-Mode vorausgesetzt)",
        requires_root=True,
        steps=(
            WorkflowStep("iface", "iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}' || echo wlan0"),
            WorkflowStep("mode_check", "iw dev wlan0 info 2>/dev/null | grep -i type || echo 'Hinweis: Monitor-Mode evtl. nötig'"),
            WorkflowStep(
                "airodump",
                f"mkdir -p {SCAN_DIR} && IFACE=$(iw dev 2>/dev/null | awk '/Interface/ {{print $2; exit}}'); "
                f"IFACE=${{IFACE:-wlan0}}; "
                f"timeout 18 airodump-ng --write {SCAN_DIR}/isaac_air --output-format csv -w {SCAN_DIR}/isaac_air \"$IFACE\" 2>&1 | head -30",
                timeout=60.0,
                optional=True,
            ),
            WorkflowStep(
                "results",
                f"ls -la {SCAN_DIR}/isaac_air* 2>/dev/null; "
                f"head -25 {SCAN_DIR}/isaac_air-01.csv 2>/dev/null || echo 'Keine CSV — Monitor-Mode prüfen'",
                optional=True,
            ),
        ),
    ),
    "lan_nmap_discovery": SecurityWorkflow(
        workflow_id="lan_nmap_discovery",
        title="LAN/Netzwerk mit Nmap entdecken",
        description="Gateway ermitteln und Subnetz scannen",
        steps=(
            WorkflowStep("routes", "ip -4 route show"),
            WorkflowStep(
                "subnet_scan",
                "GW=$(ip route | awk '/default/ {{print $3; exit}}'); "
                "SUBNET=$(ip -4 route | awk '/proto kernel/ && !/default/ {{print $1; exit}}'); "
                "echo \"Gateway: $GW Subnet: $SUBNET\"; "
                "test -n \"$SUBNET\" && nmap -sn \"$SUBNET\" 2>/dev/null | head -60 || nmap -sn \"$GW/24\" 2>/dev/null | head -60",
                timeout=180.0,
            ),
        ),
    ),
    "router_audit": SecurityWorkflow(
        workflow_id="router_audit",
        title="Router prüfen",
        description="Gateway pingen, Portscan, RouterSploit-Hinweis",
        steps=(
            WorkflowStep("gateway", "ip route | awk '/default/ {{print \"Gateway:\", $3; exit}}'"),
            WorkflowStep(
                "ping",
                "GW=$(ip route | awk '/default/ {{print $3; exit}}'); ping -c 2 -W 2 \"$GW\" 2>/dev/null",
                optional=True,
            ),
            WorkflowStep(
                "nmap_router",
                "GW=$(ip route | awk '/default/ {{print $3; exit}}'); nmap -sV -F \"$GW\" 2>/dev/null | head -40",
                timeout=120.0,
                optional=True,
            ),
            WorkflowStep(
                "routersploit_hint",
                "echo 'RouterSploit: nutze routersploit → scan oder installiere routersploit'",
                optional=True,
            ),
        ),
    ),
    "nethunter_status": SecurityWorkflow(
        workflow_id="nethunter_status",
        title="NetHunter / Kali Status",
        description="Chroot-Erkennung, CLI, Pfade, Tool-Verfügbarkeit",
        steps=(),  # dynamisch via _workflow_nethunter_status
    ),
    "nethunter_bootstrap": SecurityWorkflow(
        workflow_id="nethunter_bootstrap",
        title="NetHunter Kali bootstrap",
        description="Chroot apt update + Security-Pakete installieren",
        steps=(),  # dynamisch
    ),
}

WORKFLOW_PARSE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"scanne\s+(?:mein\s+)?wlan\s+mit\s+wifite", "wlan_wifite_scan"),
    (r"scanne\s+(?:mein\s+)?wlan\s+mit\s+aircrack", "wlan_aircrack_scan"),
    (r"analysiere\s+(?:mein\s+)?wlan", "wlan_survey"),
    (r"scanne\s+(?:mein\s+)?(?:netzwerk|lan)(?:\s+mit\s+nmap)?", "lan_nmap_discovery"),
    (r"prüfe\s+(?:mein(?:en)?\s+)?router", "router_audit"),
    (r"audit(?:iere)?\s+router", "router_audit"),
    (r"nethunter\s+(?:bootstrap|einrichten|setup|install)", "nethunter_bootstrap"),
    (r"(?:zeige|starte|nutze)\s+nethunter(?:\s+kali)?(?:\s+status)?", "nethunter_status"),
    (r"nethunter\s+status", "nethunter_status"),
    (r"workflow\s+([a-z0-9_-]+)", "workflow_id"),
)


def workflows_enabled() -> bool:
    return is_owner_equivalent_mode()


def list_workflows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for wf in WORKFLOW_REGISTRY.values():
        if wf.steps or wf.workflow_id.startswith("nethunter"):
            rows.append({
                "workflow_id": wf.workflow_id,
                "title": wf.title,
                "description": wf.description,
            })
    return rows


def match_workflow(text: str) -> Optional[dict[str, Any]]:
    if not workflows_enabled():
        return None
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    normalized = re.sub(r"^isaac[,:]\s+", "", normalized)
    for pattern, workflow_id in WORKFLOW_PARSE_PATTERNS:
        m = re.search(pattern, normalized)
        if not m:
            continue
        wid = workflow_id
        if workflow_id == "workflow_id" and m.lastindex:
            wid = m.group(1).strip()
        if wid not in WORKFLOW_REGISTRY:
            continue
        target = ""
        tm = re.search(r"(?:auf|gegen|ziel|target)\s+([^\s]+)", normalized)
        if tm:
            target = tm.group(1).strip(" .,!?")
        return {"action": "workflow", "workflow_id": wid, "target": target}
    return None


def detect_nethunter_environment() -> dict[str, Any]:
    """Erkennt NetHunter/Kali-Chroot oder natives S8/apt."""
    from computer_use import detect_runtime

    runtime = detect_runtime()
    info: dict[str, Any] = {
        "runtime": runtime,
        "mode": "none",
        "available": False,
        "chroot_path": "",
        "nethunter_cli": shutil.which("nethunter") or "",
        "kalify_cli": shutil.which("kalify-chroot") or "",
    }

    if runtime == "s8":
        info.update({"mode": "s8_native", "available": True, "note": "Native Linux-Root (apt direkt)"})
        return info

    for candidate in NETHUNTER_CHROOT_CANDIDATES:
        path = Path(candidate)
        if path.exists() and ((path / "bin").exists() or (path / "usr/bin").exists()):
            info.update({"mode": "chroot_path", "available": True, "chroot_path": str(path)})
            return info
        if path.exists():
            info.update({"mode": "chroot_path", "available": True, "chroot_path": str(path)})
            return info

    if info["nethunter_cli"]:
        info.update({"mode": "nethunter_cli", "available": True})
        return info

    if runtime == "termux" and (shutil.which("apt") or Path("/data/data/com.termux/files/usr/bin/apt").exists()):
        info.update({"mode": "termux_kali", "available": True, "note": "Termux mit apt/pkg"})
        return info

    return info


def build_chroot_command(command: str, nh: Optional[dict[str, Any]] = None) -> str:
    env = nh or detect_nethunter_environment()
    cmd = (command or "").strip()
    if not cmd:
        return ""

    if env.get("mode") == "s8_native":
        return cmd

    cli = env.get("nethunter_cli") or ""
    if cli and env.get("mode") == "nethunter_cli":
        safe = cmd.replace("'", "'\"'\"'")
        return f"{cli} -c '{safe}' 2>/dev/null || {cli} {safe} 2>/dev/null || echo 'nethunter exec fehlgeschlagen'"

    chroot = env.get("chroot_path") or ""
    if chroot and Path(chroot).exists():
        safe = cmd.replace("'", "'\"'\"'")
        return (
            f"chroot {shlex_quote(chroot)} /bin/bash -lc '{safe}' 2>/dev/null || "
            f"proot -0 -r {shlex_quote(chroot)} -b /dev -b /sys -b /proc "
            f"-b /dev/null:/dev/null /bin/bash -lc '{safe}' 2>/dev/null || "
            f"echo 'chroot/proot exec fehlgeschlagen für {chroot}'"
        )

    return cmd


def shlex_quote(value: str) -> str:
    if re.match(r"^[a-zA-Z0-9_@.:/-]+$", value or ""):
        return value
    return "'" + (value or "").replace("'", "'\"'\"'") + "'"


async def _shell(command: str, timeout: float = 90.0) -> dict[str, Any]:
    from owner_action import _shell as owner_shell

    return await owner_shell(command, timeout=timeout)


async def _run_steps(
    title: str,
    steps: tuple[WorkflowStep, ...],
    *,
    use_chroot: bool = False,
) -> tuple[str, bool]:
    nh = detect_nethunter_environment() if use_chroot else None
    lines = [f"[Workflow] {title}", ""]
    ok = True
    for step in steps:
        cmd = build_chroot_command(step.command, nh) if use_chroot else step.command
        result = await _shell(cmd, timeout=step.timeout)
        lines.append(f"## {step.name}")
        lines.append(f"$ {cmd[:200]}")
        if result.get("stdout"):
            lines.append(str(result["stdout"])[:3500])
        if result.get("stderr"):
            lines.append(f"stderr: {str(result['stderr'])[:600]}")
        if result.get("error"):
            lines.append(f"error: {result['error']}")
        step_ok = bool(result.get("ok"))
        if not step_ok and not step.optional:
            ok = False
            lines.append(f"→ Schritt fehlgeschlagen: {step.name}")
            break
        lines.append("")
    return "\n".join(lines).strip(), ok


async def _workflow_nethunter_status() -> tuple[str, bool]:
    nh = detect_nethunter_environment()
    lines = [
        "[Workflow] NetHunter / Kali Status",
        "",
        f"Modus: {nh.get('mode')}",
        f"Runtime: {nh.get('runtime')}",
        f"Verfügbar: {nh.get('available')}",
    ]
    if nh.get("chroot_path"):
        lines.append(f"Chroot: {nh['chroot_path']}")
    if nh.get("nethunter_cli"):
        lines.append(f"CLI: {nh['nethunter_cli']}")
    if nh.get("note"):
        lines.append(f"Hinweis: {nh['note']}")
    lines.append("")

    checks = (
        ("uname", "uname -a"),
        ("apt", "command -v apt || command -v apt-get"),
        ("msfconsole", "command -v msfconsole"),
        ("nmap", "command -v nmap"),
        ("aircrack", "command -v aircrack-ng"),
    )
    ok = bool(nh.get("available"))
    use_chroot = nh.get("mode") in {"chroot_path", "nethunter_cli"}
    for name, cmd in checks:
        wrapped = build_chroot_command(cmd, nh) if use_chroot else cmd
        result = await _shell(wrapped, timeout=30.0)
        status = "OK" if result.get("ok") and (result.get("stdout") or "").strip() else "—"
        detail = (result.get("stdout") or result.get("error") or "")[:120].strip()
        lines.append(f"• {name}: {status} {detail}")
        if name == "uname" and result.get("ok"):
            ok = True

    AuditLog.action("SecurityWorkflow", "nethunter_status", nh.get("mode", "none"))
    return "\n".join(lines), ok


async def _workflow_nethunter_bootstrap() -> tuple[str, bool]:
    nh = detect_nethunter_environment()
    if not nh.get("available"):
        return "[Workflow] NetHunter/Kali nicht erkannt. Native apt auf S8 oder Chroot installieren.", False

    if nh.get("mode") == "s8_native":
        pkgs = " ".join(NETHUNTER_BOOTSTRAP_PACKAGES)
        cmds = [
            f"apt-get update -qq && apt-get install -y {pkgs}",
        ]
        lines = ["[Workflow] S8 Native — Security-Pakete installieren", ""]
        ok = True
        for cmd in cmds:
            result = await _shell(cmd, timeout=600.0)
            lines.append(f"$ {cmd[:160]}")
            if result.get("stdout"):
                lines.append(str(result["stdout"])[:2000])
            ok = ok and bool(result.get("ok"))
        AuditLog.action("SecurityWorkflow", "nethunter_bootstrap", "s8_native")
        return "\n".join(lines), ok

    pkgs = " ".join(NETHUNTER_BOOTSTRAP_PACKAGES)
    steps = (
        WorkflowStep("apt_update", "apt-get update -qq", timeout=300.0),
        WorkflowStep("apt_install", f"apt-get install -y {pkgs}", timeout=600.0),
        WorkflowStep("verify", "command -v msfconsole nmap aircrack-ng | xargs -I{{}} echo OK: {{}}"),
    )
    AuditLog.action("SecurityWorkflow", "nethunter_bootstrap", nh.get("mode", "chroot"))
    return await _run_steps("NetHunter Kali Bootstrap", steps, use_chroot=True)


async def run_workflow(
    workflow_id: str,
    *,
    target: str = "",
) -> tuple[str, bool]:
    if not workflows_enabled():
        return "[Workflow] Nur im Admin-Modus verfügbar.", False

    wid = (workflow_id or "").strip().lower()
    if wid not in WORKFLOW_REGISTRY:
        return f"[Workflow] Unbekannter Workflow: {workflow_id}", False

    wf = WORKFLOW_REGISTRY[wid]
    AuditLog.action("SecurityWorkflow", "start", f"{wid} target={target[:40]}")

    if wid == "nethunter_status":
        return await _workflow_nethunter_status()
    if wid == "nethunter_bootstrap":
        return await _workflow_nethunter_bootstrap()

    if not wf.steps:
        return f"[Workflow] {wid} hat keine Schritte.", False

    # Tool-Abhängigkeiten vor Workflow installieren
    tool_deps = {
        "wlan_wifite_scan": ["wifite"],
        "wlan_aircrack_scan": ["aircrack"],
        "lan_nmap_discovery": ["nmap"],
    }
    from security_toolkit import install_tool

    for dep in tool_deps.get(wid, []):
        await install_tool(dep)

    return await _run_steps(wf.title, wf.steps)