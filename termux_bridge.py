from __future__ import annotations

"""Brücke S8-Linux-Chroot ↔ Termux/Termux:API für UI-Steuerung."""

import asyncio
import json
import logging
import os
import shlex
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR

log = logging.getLogger("Isaac.TermuxBridge")

TERMUX_HOME = Path("/data/data/com.termux/files/home")
TERMUX_PREFIX = Path("/data/data/com.termux/files/usr")
TERMUX_BIN = TERMUX_PREFIX / "bin"
TERMUX_API_TOOLS = (
    "termux-screenshot",
    "termux-clipboard-get",
    "termux-clipboard-set",
    "termux-open-url",
    "termux-battery-status",
    "termux-location",
    "termux-wake-lock",
)
ANDROID_INPUT = "input"


@dataclass(frozen=True)
class BridgeProbe:
    mode: str
    available: bool
    detail: str = ""


def termux_prefix() -> Optional[Path]:
    env = (os.getenv("ISAAC_TERMUX_PREFIX") or "").strip()
    if env:
        path = Path(env)
        if path.exists():
            return path
    return TERMUX_PREFIX if TERMUX_PREFIX.exists() else None


def termux_home() -> Path:
    env = (os.getenv("ISAAC_TERMUX_HOME") or "").strip()
    if env:
        return Path(env)
    return TERMUX_HOME


def termux_uid() -> Optional[int]:
    pkg = Path("/data/data/com.termux")
    if not pkg.exists():
        return None
    try:
        return pkg.stat().st_uid
    except OSError:
        return None


def bridge_enabled() -> bool:
    raw = (os.getenv("ISAAC_TERMUX_BRIDGE") or "auto").strip().lower()
    return raw not in {"0", "false", "off", "disabled"}


def bridge_mode() -> str:
    forced = (os.getenv("ISAAC_TERMUX_BRIDGE_MODE") or "").strip().lower()
    if forced in {"direct", "su", "ssh", "hub"}:
        return forced
    if _hub_url():
        return "hub"
    if _ssh_target_ready():
        return "ssh"
    if termux_uid() is not None and TERMUX_BIN.exists():
        return "su"
    if termux_prefix() is not None:
        return "direct"
    return "none"


def _hub_url() -> str:
    return (os.getenv("ISAAC_TERMUX_HUB_URL") or os.getenv("S8_HUB_URL") or "").strip().rstrip("/")


def _hub_token() -> str:
    return (os.getenv("ISAAC_TERMUX_HUB_TOKEN") or os.getenv("S8_HUB_TOKEN") or "").strip()


def _ssh_host() -> str:
    return (os.getenv("ISAAC_TERMUX_SSH_HOST") or "127.0.0.1").strip()


def _ssh_port() -> int:
    try:
        return int(os.getenv("ISAAC_TERMUX_SSH_PORT") or "8022")
    except ValueError:
        return 8022


def _ssh_user() -> str:
    explicit = (os.getenv("ISAAC_TERMUX_SSH_USER") or "").strip()
    if explicit:
        return explicit
    return "u0_a0"


def _ssh_identity() -> str:
    return (os.getenv("ISAAC_TERMUX_SSH_IDENTITY") or str(DATA_DIR / "termux_bridge_id")).strip()


def _ssh_target_ready() -> bool:
    identity = Path(_ssh_identity())
    return identity.exists() and identity.stat().st_size > 0


def termux_tool_path(name: str) -> Optional[Path]:
    prefix = termux_prefix()
    if not prefix:
        return None
    candidate = prefix / "bin" / name
    return candidate if candidate.exists() else None


def bridge_work_dir() -> Path:
    home = termux_home()
    if home.exists():
        path = home / ".isaac" / "bridge"
    else:
        path = DATA_DIR / "termux_bridge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _shell_quote(value: str) -> str:
    return shlex.quote(value)


def _termux_shell_command(command: str) -> str:
    prefix = str(termux_prefix() or TERMUX_PREFIX)
    home = str(termux_home())
    inner = (
        f"export PREFIX={_shell_quote(prefix)}; "
        f"export HOME={_shell_quote(home)}; "
        f"export PATH=$PREFIX/bin:$PATH; "
        f"{command}"
    )
    uid = termux_uid()
    if uid is not None:
        return f"su {uid} -c {_shell_quote(inner)}"
    return f"run-as com.termux sh -c {_shell_quote(inner)}"


async def _run_shell(command: str, *, timeout: float = 30.0) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"ok": False, "error": f"Timeout ({int(timeout)}s)", "command": command}
    out = (stdout or b"").decode(errors="replace")
    err = (stderr or b"").decode(errors="replace")
    return {
        "ok": proc.returncode == 0,
        "command": command,
        "stdout": out,
        "stderr": err,
        "exit_code": proc.returncode,
    }


async def _run_direct(argv: list[str], *, timeout: float = 30.0) -> dict[str, Any]:
    if not argv:
        return {"ok": False, "error": "Leeres Kommando"}
    tool = termux_tool_path(argv[0])
    if not tool:
        return {"ok": False, "error": f"Termux-Tool fehlt: {argv[0]}"}
    proc = await asyncio.create_subprocess_exec(
        str(tool),
        *argv[1:],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            **os.environ,
            "PREFIX": str(termux_prefix() or TERMUX_PREFIX),
            "HOME": str(termux_home()),
            "PATH": f"{termux_prefix() or TERMUX_PREFIX}/bin:" + os.environ.get("PATH", ""),
        },
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"ok": False, "error": f"Timeout ({int(timeout)}s)", "argv": argv}
    return {
        "ok": proc.returncode == 0,
        "argv": argv,
        "stdout": (stdout or b"").decode(errors="replace"),
        "stderr": (stderr or b"").decode(errors="replace"),
        "exit_code": proc.returncode,
        "via": "direct",
    }


async def _run_su(command: str, *, timeout: float = 30.0) -> dict[str, Any]:
    result = await _run_shell(_termux_shell_command(command), timeout=timeout)
    result["via"] = "su"
    return result


async def _run_ssh(command: str, *, timeout: float = 30.0) -> dict[str, Any]:
    identity = _ssh_identity()
    target = f"{_ssh_user()}@{_ssh_host()}"
    remote = (
        f"export PREFIX=$HOME/../usr; export PATH=$PREFIX/bin:$PATH; {command}"
    )
    proc = await asyncio.create_subprocess_exec(
        "ssh",
        "-i",
        identity,
        "-p",
        str(_ssh_port()),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        target,
        remote,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"ok": False, "error": f"SSH Timeout ({int(timeout)}s)"}
    return {
        "ok": proc.returncode == 0,
        "stdout": (stdout or b"").decode(errors="replace"),
        "stderr": (stderr or b"").decode(errors="replace"),
        "exit_code": proc.returncode,
        "via": "ssh",
    }


async def _run_hub(argv: list[str], *, timeout: float = 30.0) -> dict[str, Any]:
    base = _hub_url()
    if not base:
        return {"ok": False, "error": "Hub-URL fehlt (ISAAC_TERMUX_HUB_URL)"}
    payload = json.dumps({"argv": argv}).encode("utf-8")
    url = f"{base}/termux/exec"
    if _hub_token():
        url = f"{url}?token={urllib.parse.quote(_hub_token())}"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return {"ok": False, "error": f"Hub HTTP {exc.code}: {detail}", "via": "hub"}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "via": "hub"}
    result = body.get("result") or body
    result["via"] = "hub"
    result["ok"] = bool(result.get("ok"))
    return result


async def run_termux_command(
    argv: list[str],
    *,
    timeout: float = 30.0,
    mode: Optional[str] = None,
) -> dict[str, Any]:
    if not bridge_enabled():
        return {"ok": False, "error": "Termux-Brücke deaktiviert (ISAAC_TERMUX_BRIDGE=0)"}
    if not argv:
        return {"ok": False, "error": "Leeres Kommando"}
    selected = mode or bridge_mode()
    attempts: list[str] = []
    if selected == "hub":
        attempts = ["hub", "ssh", "su", "direct"]
    elif selected == "ssh":
        attempts = ["ssh", "su", "direct", "hub"]
    elif selected == "su":
        attempts = ["su", "direct", "ssh", "hub"]
    elif selected == "direct":
        attempts = ["direct", "su", "ssh", "hub"]
    else:
        attempts = ["su", "direct", "ssh", "hub"]

    command = " ".join(_shell_quote(part) for part in argv)
    errors: list[str] = []
    for attempt in attempts:
        if attempt == "direct":
            result = await _run_direct(argv, timeout=timeout)
        elif attempt == "su":
            if termux_uid() is None and not TERMUX_BIN.exists():
                errors.append("su: termux nicht gefunden")
                continue
            result = await _run_su(command, timeout=timeout)
        elif attempt == "ssh":
            if not _ssh_target_ready():
                errors.append("ssh: identity fehlt")
                continue
            result = await _run_ssh(command, timeout=timeout)
        elif attempt == "hub":
            if not _hub_url():
                errors.append("hub: url fehlt")
                continue
            result = await _run_hub(argv, timeout=timeout)
        else:
            continue
        if result.get("ok"):
            return result
        errors.append(f"{attempt}: {(result.get('stderr') or result.get('error') or 'fail')[:160]}")
    return {"ok": False, "error": "Termux-Brücke fehlgeschlagen | " + " | ".join(errors[:4])}


async def run_android_input(argv: list[str], *, timeout: float = 15.0) -> dict[str, Any]:
    if not argv:
        return {"ok": False, "error": "Leeres input-Kommando"}
    # tsu/input nur auf Android-Schicht verfügbar — über Termux ausführen.
    tsu_cmd = "tsu -c " + _shell_quote(" ".join([ANDROID_INPUT, *argv]))
    result = await run_termux_command(["sh", "-c", tsu_cmd], timeout=timeout)
    if result.get("ok"):
        result["via"] = f"{result.get('via', 'termux')}+input"
        return result
    fallback = " ".join([ANDROID_INPUT, *argv])
    result = await run_termux_command(["sh", "-c", fallback], timeout=timeout)
    if result.get("ok"):
        result["via"] = f"{result.get('via', 'termux')}+input"
    return result


async def run_ui_dump(*, timeout: float = 35.0) -> dict[str, Any]:
    dump_path = bridge_work_dir() / "isaac_ui.xml"
    remote = str(dump_path)
    commands = (
        f"tsu -c {_shell_quote(f'uiautomator dump {remote} && cat {remote}')}",
        f"uiautomator dump {remote} && cat {remote}",
        f"adb shell uiautomator dump {remote} && adb shell cat {remote}",
    )
    errors: list[str] = []
    for command in commands:
        result = await run_termux_command(["sh", "-c", command], timeout=timeout)
        if result.get("ok") and (result.get("stdout") or "").strip():
            return result
        errors.append((result.get("stderr") or result.get("error") or "leer")[:120])
    return {"ok": False, "error": "UI-Dump über Termux fehlgeschlagen | " + " | ".join(errors)}


def bridge_available() -> bool:
    if not bridge_enabled():
        return False
    return bridge_mode() != "none" or termux_prefix() is not None


def diagnose_bridge() -> dict[str, Any]:
    probes = [
        BridgeProbe("termux_prefix", termux_prefix() is not None, str(termux_prefix() or "-")),
        BridgeProbe("termux_uid", termux_uid() is not None, str(termux_uid() or "-")),
        BridgeProbe("ssh_identity", _ssh_target_ready(), _ssh_identity()),
        BridgeProbe("hub_url", bool(_hub_url()), _hub_url() or "-"),
    ]
    tools: dict[str, bool] = {}
    for name in (*TERMUX_API_TOOLS, ANDROID_INPUT, "tsu", "uiautomator", "adb"):
        tools[name] = termux_tool_path(name) is not None
    return {
        "enabled": bridge_enabled(),
        "mode": bridge_mode(),
        "home": str(termux_home()),
        "work_dir": str(bridge_work_dir()),
        "probes": [probe.__dict__ for probe in probes],
        "tools": tools,
    }


