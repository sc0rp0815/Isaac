#!/usr/bin/env python3
"""S8+ Remote Hub — iPhone-Zugang zu Termux, Isaac und lokalen Agenten.

Nur für eigene Geräte. Token-Pflicht (außer /health).
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

VERSION = "1.0.0"
DEFAULT_PORT = int(os.getenv("S8_HUB_PORT", "8768"))
DEFAULT_BIND = os.getenv("S8_HUB_BIND", "0.0.0.0")
TOKEN = os.getenv("S8_HUB_TOKEN", "").strip()
CONFIG_PATH = Path(os.getenv("S8_HUB_CONFIG", Path(__file__).resolve().parent / "agents.json"))
ALLOWED_TERMUX_COMMANDS = frozenset({
    "termux-screenshot",
    "termux-clipboard-get",
    "termux-clipboard-set",
    "termux-open-url",
    "termux-battery-status",
    "termux-location",
    "termux-wake-lock",
    "input",
    "sh",
    "uiautomator",
    "adb",
    "tsu",
})


def expand(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.is_file():
        with CONFIG_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)
    return {"agents": [], "shell_globs": [], "unix_sockets": [], "file_roots": [], "screen": {}}


def check_token(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> bool:
    if not TOKEN:
        return True
    supplied = (
        handler.headers.get("X-Hub-Token")
        or handler.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        or (query.get("token") or [""])[0]
    )
    return supplied == TOKEN


def run_cmd(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def http_get(url: str, timeout: int = 8) -> dict[str, Any]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {"raw": body[:4000]}
            return {"ok": True, "status": resp.status, "data": data}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def discover_shell_agents(globs: list[str]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for pattern in globs:
        for match in sorted(glob.glob(os.path.expanduser(pattern))):
            p = Path(match)
            if p.is_file() and os.access(p, os.X_OK):
                found.append({
                    "id": p.stem,
                    "label": p.name,
                    "type": "shell",
                    "path": str(p),
                })
    return found


def discover_unix_agents(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for entry in entries:
        if not entry.get("enabled"):
            continue
        sock = expand(str(entry.get("path", "")))
        if sock.exists():
            found.append({
                "id": str(entry.get("id", sock.name)),
                "label": str(entry.get("label", sock.name)),
                "type": "unix",
                "path": str(sock),
            })
    return found


def allowed_file(path: Path, roots: list[str]) -> bool:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(expand(root))
            return True
        except ValueError:
            continue
    return False


def tailscale_ip() -> str:
    res = run_cmd(["tailscale", "ip", "-4"], timeout=5)
    if res.get("ok") and res.get("stdout"):
        return res["stdout"].splitlines()[0].strip()
    return ""


class HubHandler(BaseHTTPRequestHandler):
    server_version = f"S8RemoteHub/{VERSION}"

    def _query(self) -> dict[str, list[str]]:
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

    def _route(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path.rstrip("/") or "/", urllib.parse.parse_qs(parsed.query)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _unauthorized(self) -> None:
        self._send(401, {"ok": False, "error": "token fehlt oder ungültig"})

    def do_GET(self) -> None:
        path, query = self._route()
        cfg = load_config()

        if path != "/health" and not check_token(self, query):
            return self._unauthorized()

        if path == "/health":
            return self._send(200, {"ok": True, "service": "s8_remote_hub", "version": VERSION})

        if path == "/status":
            isaac = http_get("http://127.0.0.1:8766/api/monitor/state")
            return self._send(200, {
                "ok": True,
                "hub": VERSION,
                "tailscale_ip": tailscale_ip(),
                "token_required": bool(TOKEN),
                "isaac_reachable": isaac.get("ok", False),
                "screen": cfg.get("screen", {}),
            })

        if path == "/location":
            loc = run_cmd(["termux-location"], timeout=20)
            if loc.get("ok") and loc.get("stdout"):
                try:
                    loc["data"] = json.loads(loc["stdout"])
                except json.JSONDecodeError:
                    pass
            return self._send(200, loc)

        if path == "/agents":
            http_agents = [a for a in cfg.get("agents", []) if a.get("enabled", True)]
            shell_agents = discover_shell_agents(cfg.get("shell_globs", []))
            unix_agents = discover_unix_agents(cfg.get("unix_sockets", []))
            return self._send(200, {
                "ok": True,
                "http": http_agents,
                "shell": shell_agents,
                "unix": unix_agents,
            })

        if path.startswith("/agents/") and path.endswith("/health"):
            agent_id = path.split("/")[2]
            for agent in cfg.get("agents", []):
                if agent.get("id") != agent_id:
                    continue
                base = agent.get("base_url", "").rstrip("/")
                health = agent.get("health_path", "/")
                return self._send(200, {
                    "ok": True,
                    "agent": agent_id,
                    "probe": http_get(f"{base}{health}"),
                })
            for agent in discover_shell_agents(cfg.get("shell_globs", [])):
                if agent["id"] == agent_id:
                    probe = run_cmd([agent["path"], "health"], timeout=15)
                    return self._send(200, {"ok": True, "agent": agent_id, "probe": probe})
            return self._send(404, {"ok": False, "error": f"agent nicht gefunden: {agent_id}"})

        if path == "/isaac/status":
            return self._send(200, http_get("http://127.0.0.1:8766/api/monitor/state"))

        if path == "/isaac/tools":
            return self._send(200, http_get("http://127.0.0.1:8766/api/tools/live"))

        if path == "/screen/info":
            info = dict(cfg.get("screen", {}))
            info["tailscale_ip"] = tailscale_ip()
            info["vnc_url"] = f"vnc://{info['tailscale_ip']}:{info.get('vnc_port', 5900)}" if info.get("tailscale_ip") else ""
            return self._send(200, {"ok": True, "screen": info})

        if path == "/files/list":
            rel = (query.get("path") or ["~/storage/downloads"])[0]
            target = expand(rel)
            if not allowed_file(target, cfg.get("file_roots", [])):
                return self._send(403, {"ok": False, "error": "pfad nicht erlaubt"})
            if not target.exists():
                return self._send(404, {"ok": False, "error": "pfad existiert nicht"})
            entries = []
            for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
                try:
                    stat = child.stat()
                    entries.append({
                        "name": child.name,
                        "path": str(child),
                        "dir": child.is_dir(),
                        "size": stat.st_size,
                    })
                except OSError:
                    continue
            return self._send(200, {"ok": True, "path": str(target), "entries": entries})

        if path == "/files/download":
            rel = (query.get("path") or [""])[0]
            if not rel:
                return self._send(400, {"ok": False, "error": "path fehlt"})
            target = expand(rel)
            if not target.is_file() or not allowed_file(target, cfg.get("file_roots", [])):
                return self._send(403, {"ok": False, "error": "datei nicht erlaubt"})
            data = target.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            return self._send(200, {
                "ok": True,
                "path": str(target),
                "size": len(data),
                "base64": b64,
            })

        return self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path, query = self._route()
        if not check_token(self, query):
            return self._unauthorized()
        cfg = load_config()
        body = self._read_json()

        if path == "/termux/exec":
            argv = body.get("argv") or []
            if not isinstance(argv, list) or not argv:
                return self._send(400, {"ok": False, "error": "argv fehlt"})
            command = str(argv[0] or "").strip()
            if command not in ALLOWED_TERMUX_COMMANDS:
                return self._send(403, {"ok": False, "error": f"befehl nicht erlaubt: {command}"})
            cmd = [str(part) for part in argv]
            return self._send(200, {"ok": True, "result": run_cmd(cmd, timeout=int(body.get("timeout", 30)))})

        if path == "/camera":
            camera = str(body.get("camera", (query.get("camera") or ["0"])[0]))
            out = expand(f"~/storage/downloads/hub_cam_{camera}.jpg")
            out.parent.mkdir(parents=True, exist_ok=True)
            res = run_cmd(["termux-camera-photo", "-c", camera, str(out)], timeout=25)
            payload: dict[str, Any] = {"ok": res.get("ok", False), "file": str(out), **res}
            if res.get("ok") and out.is_file():
                payload["base64"] = base64.b64encode(out.read_bytes()).decode("ascii")
            return self._send(200, payload)

        if path.startswith("/agents/") and path.endswith("/invoke"):
            agent_id = path.split("/")[2]
            for agent in cfg.get("agents", []):
                if agent.get("id") != agent_id or agent.get("type") != "http":
                    continue
                base = agent.get("base_url", "").rstrip("/")
                endpoint = body.get("path", "/api/mcp/tools/invoke")
                url = f"{base}{endpoint}"
                try:
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(body.get("payload", {})).encode("utf-8"),
                        headers={"Content-Type": "application/json", "Accept": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        data = json.loads(resp.read().decode("utf-8", errors="replace"))
                    return self._send(200, {"ok": True, "agent": agent_id, "data": data})
                except Exception as exc:
                    return self._send(502, {"ok": False, "agent": agent_id, "error": str(exc)})

            for agent in discover_shell_agents(cfg.get("shell_globs", [])):
                if agent["id"] != agent_id:
                    continue
                args = body.get("args", [])
                cmd = [agent["path"], *([str(a) for a in args] if isinstance(args, list) else [])]
                return self._send(200, {"ok": True, "agent": agent_id, "result": run_cmd(cmd, timeout=30)})

            for agent in discover_unix_agents(cfg.get("unix_sockets", [])):
                if agent["id"] != agent_id:
                    continue
                msg = (body.get("message") or "ping").encode("utf-8")
                try:
                    sock = expand(agent["path"])
                    proc = subprocess.run(
                        ["socat", "-", f"UNIX-CONNECT:{sock}"],
                        input=msg,
                        capture_output=True,
                        timeout=10,
                    )
                    return self._send(200, {
                        "ok": proc.returncode == 0,
                        "stdout": proc.stdout.decode("utf-8", errors="replace"),
                        "stderr": proc.stderr.decode("utf-8", errors="replace"),
                    })
                except Exception as exc:
                    return self._send(502, {"ok": False, "error": str(exc)})

            return self._send(404, {"ok": False, "error": f"agent nicht gefunden: {agent_id}"})

        return self._send(404, {"ok": False, "error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[hub] %s - %s\n" % (self.address_string(), fmt % args))


def main() -> int:
    parser = argparse.ArgumentParser(description="S8+ Remote Hub")
    parser.add_argument("--bind", default=DEFAULT_BIND)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    if not TOKEN:
        print("WARNUNG: S8_HUB_TOKEN nicht gesetzt — Hub ist ohne Auth erreichbar.", file=sys.stderr)

    server = ThreadingHTTPServer((args.bind, args.port), HubHandler)
    print(f"S8 Remote Hub auf http://{args.bind}:{args.port}")
    print(f"Config: {CONFIG_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nHub beendet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())