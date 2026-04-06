"""
Isaac – Monitor Server v2.0
=============================
Fixes:
  - Callbacks vollständig thread-safe via asyncio.ensure_future
  - Empathie-Status im Dashboard
  - Blacklist-Status im Provider-Tab
  - Watchdog-Status in Metriken
  - _on_task_update und _on_audit_event laufen sicher im Loop
"""

import asyncio
import json
import os
import time
import logging
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol
from pathlib import Path
import socket

from config   import get_config, Level
from privilege import get_gate, steffen_ctx
from audit    import AuditLog
from task_tool_state import get_task_tool_state_store
from memory   import get_memory
from executor import get_executor, TaskType, TaskStatus
from relay    import get_relay
from logic    import get_logic

log = logging.getLogger("Isaac.Monitor")
_kernel_ref = None

def set_kernel(kernel):
    global _kernel_ref
    _kernel_ref = kernel


def _is_port_in_use(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except Exception:
        return False


def _request_json(request):
    async def _inner():
        try:
            return await request.json()
        except Exception:
            return {}
    return _inner()


def _public_ws_host(request, mon):
    env_host = os.getenv("MONITOR_WS_HOST_PUBLIC", "").strip()
    if env_host:
        return env_host
    try:
        req_host = request.host.split(":", 1)[0].strip()
    except Exception:
        req_host = ""
    if req_host and req_host not in {"localhost", "127.0.0.1", "::1"}:
        return req_host
    host = mon.bound_host or req_host or get_config().monitor.host
    if host in {"localhost", "::1", "0.0.0.0", ""}:
        return "127.0.0.1"
    return host


class MonitorServer:
    def __init__(self):
        self.cfg      = get_config()
        self.clients: set[WebSocketServerProtocol] = set()
        self.executor = get_executor()
        self.relay    = get_relay()
        self.memory   = get_memory()
        self.logic    = get_logic()
        self.gate     = get_gate()
        self._loop:   Optional[asyncio.AbstractEventLoop] = None
        self._push:   Optional[asyncio.Task] = None
        self.bound_host = self.cfg.monitor.host
        self.bound_port = self.cfg.monitor.port

        # Callbacks: werden aufgerufen aus sync Executor-Code
        # → müssen thread-safe sein
        self.executor.register_callback(self._on_task_update_sync)
        AuditLog.register_callback(self._on_audit_event_sync)

        log.info(f"MonitorServer v2.0 │ ws://{self.cfg.monitor.host}:{self.cfg.monitor.port}")

    async def start(self):
        self._loop = asyncio.get_running_loop()
        self._push = asyncio.create_task(self._metric_pusher())

        host = self.cfg.monitor.host
        start_port = int(os.getenv("MONITOR_PORT", str(self.cfg.monitor.port)))
        last_error = None

        for offset in range(0, 10):
            port = start_port + offset
            try:
                async with websockets.serve(
                    self._handle_client,
                    host,
                    port,
                    max_size=10 * 1024 * 1024,
                    ping_interval=20,
                    ping_timeout=30,
                ):
                    self.bound_host = host
                    self.bound_port = port
                    if offset:
                        log.warning(f"WS-Port {start_port} belegt → Fallback auf {port}")
                    log.info(f"WS aktiv: ws://{host}:{port}")
                    await asyncio.Future()
            except OSError as e:
                last_error = e
                if e.errno == 98 or "address already in use" in str(e).lower():
                    continue
                raise

        raise last_error or RuntimeError("Kein freier WS-Port gefunden")

    # ── Callbacks (sync, thread-safe) ─────────────────────────────────────────
    def _on_task_update_sync(self, task_dict: dict):
        """
        Wird vom Executor synchron aufgerufen.
        Leitet sicher in den Event Loop weiter.
        """
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"typ": "task_update", "task": task_dict}),
                self._loop
            )

    def _on_audit_event_sync(self, entry: dict):
        """Wie _on_task_update_sync — thread-safe."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"typ": "audit_event", "entry": entry}),
                self._loop
            )

    # ── Client-Handler ─────────────────────────────────────────────────────────
    async def _handle_client(self, ws: WebSocketServerProtocol):
        path = getattr(ws, "path", "/")
        self.clients.add(ws)
        log.info(f"Client: {ws.remote_address}")

        await self._send(ws, {"typ": "init", "state": self._build_state()})
        await self._send(ws, {"typ": "tasks", "tasks": self.executor.all_tasks(100)})
        await self._send(ws, {"typ": "audit", "entries": AuditLog.recent(60)})

        try:
            async for raw in ws:
                try:
                    await self._handle_msg(ws, json.loads(raw))
                except json.JSONDecodeError:
                    await self._send(ws, {"typ": "fehler", "msg": "Ungültiges JSON"})
                except Exception as e:
                    log.error(f"Message-Handler: {e}")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)

    async def _handle_msg(self, ws: WebSocketServerProtocol, msg: dict):
        t = msg.get("typ", "")
        if   t == "chat":             await self._handle_chat(ws, msg)
        elif t == "task_cancel":      await self._handle_cancel(ws, msg)
        elif t == "directive_add":    await self._handle_directive_add(ws, msg)
        elif t == "directive_revoke": await self._handle_directive_revoke(ws, msg)
        elif t == "fact_set":
            self.memory.set_fact(msg.get("key",""), msg.get("value",""), source="Steffen")
            await self._send(ws, {"typ": "ok", "msg": "Fakt gespeichert"})
        elif t == "pause":
            self.gate.pause(steffen_ctx("Dashboard-Pause"))
            await self._broadcast({"typ": "system", "event": "paused"})
        elif t == "resume":
            self.gate.resume(steffen_ctx("Dashboard-Resume"))
            await self._broadcast({"typ": "system", "event": "resumed"})
        elif t == "state_request":
            await self._send(ws, {"typ": "state", "state": self._build_state()})
        elif t == "tasks_request":
            await self._send(ws, {"typ": "tasks", "tasks": self.executor.all_tasks(200)})
        elif t == "audit_request":
            await self._send(ws, {"typ": "audit", "entries": AuditLog.recent(msg.get("n", 100))})
        elif t == "ping":
            await self._send(ws, {"typ": "pong", "ts": time.strftime("%H:%M:%S")})

    async def _handle_chat(self, ws, msg: dict):
        text = msg.get("text", "").strip()
        if not text: return
        AuditLog.steffen_input(text)
        if _kernel_ref:
            asyncio.create_task(self._process_input(ws, text))
        else:
            await self._send(ws, {"typ": "chat_response",
                                  "text": "[Monitor] Kernel nicht bereit",
                                  "ts": time.strftime("%H:%M:%S")})

    async def _process_input(self, ws, text: str):
        try:
            antwort = await _kernel_ref.process(text)
            AuditLog.isaac_output(antwort)
            await self._send(ws, {"typ": "chat_response",
                                  "text": antwort,
                                  "ts":   time.strftime("%H:%M:%S")})
        except Exception as e:
            await self._send(ws, {"typ": "chat_response",
                                  "text": f"[Fehler] {e}",
                                  "ts":   time.strftime("%H:%M:%S")})

    async def _handle_cancel(self, ws, msg: dict):
        tid  = msg.get("task_id", "")
        task = self.executor.get_task(tid)
        if task:
            task.status = TaskStatus.CANCELLED
            task.log("Dashboard: abgebrochen")
            await self._send(ws, {"typ": "ok", "msg": f"Task {tid} abgebrochen"})
            self.executor._notify(task)

    async def _handle_directive_add(self, ws, msg: dict):
        text = msg.get("text", "")
        pri  = int(msg.get("priority", 10))
        if not text: return
        d = self.gate.add_directive(text, pri)
        self.memory.save_directive(d.id, d.text, d.priority)
        await self._send(ws, {"typ": "ok", "msg": f"Direktive {d.id} gesetzt"})
        await self._broadcast({"typ": "directives",
                               "directives": self._get_directives()})

    async def _handle_directive_revoke(self, ws, msg: dict):
        did = msg.get("id", "")
        self.gate.revoke_directive(did)
        self.memory.revoke_directive(did)
        await self._send(ws, {"typ": "ok", "msg": f"Direktive {did} widerrufen"})
        await self._broadcast({"typ": "directives",
                               "directives": self._get_directives()})

    # ── State ──────────────────────────────────────────────────────────────────
    def _build_state(self) -> dict:
        # Empathie und Watchdog lazy laden
        empathie_status = {}
        watchdog_status = {}
        blacklist_status = []
        try:
            from empathie import get_empathie
            empathie_status = get_empathie().status_dict()
        except Exception: pass
        try:
            from watchdog import get_watchdog, get_blacklist
            watchdog_status  = get_watchdog().stats()
            blacklist_status = get_blacklist().all_stats()
        except Exception: pass

        provider_configs = {}
        for name, cfg in getattr(self.cfg, "providers", {}).items():
            provider_configs[name] = {
                "enabled": bool(getattr(cfg, "enabled", False)),
                "available": bool(getattr(cfg, "available", False)),
                "default_model": getattr(cfg, "default_model", ""),
                "base_url": getattr(cfg, "base_url", ""),
                "timeout": getattr(cfg, "timeout", None),
                "rpm": getattr(cfg, "rpm", None),
                "tpm": getattr(cfg, "tpm", None),
            }

        tools_status = []
        try:
            from tool_registry import get_tool_registry
            tools_status = get_tool_registry().list_tools()
        except Exception:
            pass

        settings = {
            "owner_name": getattr(self.cfg, "owner_name", "Steffen"),
            "active_provider": getattr(getattr(self.cfg, "relay", None), "primary_provider", ""),
            "monitor_host": self.bound_host,
            "monitor_port": self.bound_port,
            "monitor_push_interval": getattr(getattr(self.cfg, "monitor", None), "push_interval", None),
            "dashboard_port": getattr(get_dashboard(), "bound_port", None),
            "memory_max_working": getattr(getattr(self.cfg, "memory", None), "max_working_memory", None),
            "memory_max_facts": getattr(getattr(self.cfg, "memory", None), "max_facts", None),
            "browser_headless": getattr(getattr(self.cfg, "browser", None), "headless", None),
            "browser_max_instances": getattr(getattr(self.cfg, "browser", None), "max_instances", None),
        }

        return {
            "ts":          time.strftime("%H:%M:%S"),
            "paused":      self.gate.is_paused,
            "memory":      self.memory.stats(),
            "executor":    self.executor.stats(),
            "logic":       self.logic.stats(),
            "audit":       AuditLog.stats(),
            "providers":   self.relay.provider_status(),
            "tools":       tools_status,
            "provider_configs": provider_configs,
            "settings":    settings,
            "gate":        self.gate.status_dict(),
            "running":     self.executor.running_tasks(),
            "directives":  self._get_directives(),
            "empathie":    empathie_status,
            "watchdog":    watchdog_status,
            "blacklist":   blacklist_status,
        }

    def _get_directives(self) -> list[dict]:
        return [{"id": d.id, "text": d.text, "priority": d.priority}
                for d in self.gate.active_directives()]

    async def _metric_pusher(self):
        interval = self.cfg.monitor.push_interval
        while True:
            await asyncio.sleep(interval)
            if self.clients:
                await self._broadcast({"typ": "state", "state": self._build_state()})

    # ── Senden ────────────────────────────────────────────────────────────────
    async def _send(self, ws, data: dict):
        try:
            await ws.send(json.dumps(data, ensure_ascii=False, default=str))
        except Exception:
            pass

    async def _broadcast(self, data: dict):
        if not self.clients: return
        payload = json.dumps(data, ensure_ascii=False, default=str)
        dead    = set()
        for ws in list(self.clients):
            try:
                await ws.send(payload)
            except Exception:
                dead.add(ws)
        self.clients -= dead


# ── HTTP Dashboard ─────────────────────────────────────────────────────────────
class DashboardHTTPServer:
    def __init__(self, port: int = 8766):
        self.port      = int(os.getenv("MONITOR_HTTP_PORT", str(port)))
        self.bound_port = None
        self.html_path = Path(__file__).parent / "dashboard.html"

    async def start(self):
        try:
            from aiohttp import web
            from tool_registry import get_tool_registry
            from secrets_store import get_secrets_store
            from tool_runtime import select_tool_for_prompt
            from tool_catalog import list_local_tool_catalog, registry_payload_from_catalog
            from mcp_registry import get_mcp_registry
            from updater import list_packages, inspect_package, apply_package, rollback_last_backup, status as updater_status, schedule_process_restart

            registry = get_tool_registry()
            secrets = get_secrets_store()
            mcp = get_mcp_registry()

            async def serve(request):
                if self.html_path.exists():
                    return web.FileResponse(self.html_path)
                return web.Response(text="Dashboard nicht gefunden", status=404)

            async def monitor_config(request):
                mon = get_monitor()
                return web.json_response({
                    "ws_host": _public_ws_host(request, mon),
                    "ws_port": mon.bound_port,
                    "http_port": self.bound_port,
                    "ws_port_candidates": list(range(int(os.getenv("MONITOR_PORT", str(get_config().monitor.port))), int(os.getenv("MONITOR_PORT", str(get_config().monitor.port))) + 10)),
                })

            async def list_tools(request):
                return web.json_response({"ok": True, "tools": registry.list_tools()})

            async def list_local_catalog(request):
                items = list_local_tool_catalog()
                installed_catalog_ids = {((t.get("metadata") or {}).get("catalog_id")) for t in registry.list_tools()}
                for item in items:
                    item["installed"] = item.get("catalog_id") in installed_catalog_ids
                return web.json_response({"ok": True, "items": items})

            async def live_tools(request):
                from tool_runtime import list_live_tool_interfaces
                live = await list_live_tool_interfaces()
                return web.json_response({"ok": True, "live": live})

            async def install_local_tool(request):
                data = await _request_json(request)
                catalog_id = (data.get("catalog_id") or "").strip()
                if not catalog_id:
                    return web.json_response({"ok": False, "error": "catalog_id fehlt"}, status=400)
                try:
                    payload = registry_payload_from_catalog(catalog_id)
                    tool = registry.add(payload)
                except KeyError as e:
                    return web.json_response({"ok": False, "error": str(e)}, status=404)
                row = next(x for x in registry.list_tools() if x["tool_id"] == tool.tool_id)
                return web.json_response({"ok": True, "tool": row, "installed": catalog_id})

            async def add_tool(request):
                data = await _request_json(request)
                api_key = (data.pop("api_key", "") or "").strip()
                if not data.get("name") or not data.get("kind"):
                    return web.json_response({"ok": False, "error": "name und kind sind Pflicht"}, status=400)
                tool = registry.add(data)
                if api_key:
                    ref = f"{tool.tool_id}_secret"
                    secrets.set_secret(ref, api_key)
                    registry.update(tool.tool_id, {"secret_ref": ref})
                row = next(x for x in registry.list_tools() if x["tool_id"] == tool.tool_id)
                return web.json_response({"ok": True, "tool": row})

            async def update_tool(request):
                data = await _request_json(request)
                tool_id = (data.get("tool_id") or "").strip()
                if not tool_id:
                    return web.json_response({"ok": False, "error": "tool_id fehlt"}, status=400)
                api_key = (data.pop("api_key", "") or "").strip()
                patch = {k: v for k, v in data.items() if k != "tool_id"}
                try:
                    tool = registry.update(tool_id, patch)
                except KeyError as e:
                    return web.json_response({"ok": False, "error": str(e)}, status=404)
                if api_key:
                    ref = tool.secret_ref or f"{tool.tool_id}_secret"
                    secrets.set_secret(ref, api_key)
                    registry.update(tool.tool_id, {"secret_ref": ref})
                row = next(x for x in registry.list_tools() if x["tool_id"] == tool.tool_id)
                return web.json_response({"ok": True, "tool": row})

            async def delete_tool(request):
                data = await _request_json(request)
                return web.json_response({"ok": registry.delete((data.get("tool_id") or "").strip())})

            async def toggle_tool(request):
                data = await _request_json(request)
                tool_id = (data.get("tool_id") or "").strip()
                try:
                    tool = registry.update(tool_id, {"active": bool(data.get("active", True))})
                except KeyError as e:
                    return web.json_response({"ok": False, "error": str(e)}, status=404)
                row = next(x for x in registry.list_tools() if x["tool_id"] == tool.tool_id)
                return web.json_response({"ok": True, "tool": row})

            async def suggest_tool(request):
                data = await _request_json(request)
                prompt = (data.get("prompt") or "").strip()
                tool = select_tool_for_prompt(prompt)
                if not tool:
                    return web.json_response({"ok": False, "error": "Kein passendes Tool"}, status=404)
                row = next(x for x in registry.list_tools() if x["tool_id"] == tool.tool_id)
                return web.json_response({"ok": True, "tool": row})


            async def mcp_capabilities(request):
                return web.json_response({"ok": True, "capabilities": mcp.capabilities()})

            async def mcp_resources(request):
                return web.json_response({"ok": True, "resources": mcp.resources()})

            async def mcp_read_resource(request):
                data = await _request_json(request)
                uri = (data.get("uri") or "").strip()
                params = dict(data.get("params") or {})
                result = mcp.read_resource(uri, **params)
                return web.json_response(result, status=200 if result.get("ok") else 404)

            async def mcp_prompts(request):
                return web.json_response({"ok": True, "prompts": mcp.prompts()})

            async def mcp_get_prompt(request):
                data = await _request_json(request)
                name = (data.get("name") or "").strip()
                args = dict(data.get("arguments") or {})
                result = mcp.get_prompt(name, args)
                return web.json_response(result, status=200 if result.get("ok") else 404)

            async def mcp_tools(request):
                return web.json_response({"ok": True, "tools": mcp.tools()})

            async def mcp_invoke_tool(request):
                data = await _request_json(request)
                name = (data.get("name") or "").strip()
                args = dict(data.get("arguments") or {})
                result = mcp.invoke_tool(name, args)
                return web.json_response(result, status=200 if result.get("ok") else 400)

            async def updater_packages(request):
                return web.json_response({"ok": True, "packages": list_packages()})

            async def updater_inspect(request):
                data = await _request_json(request)
                package_name = (data.get("package") or "").strip()
                if not package_name:
                    return web.json_response({"ok": False, "error": "package fehlt"}, status=400)
                try:
                    return web.json_response(inspect_package(package_name))
                except Exception as e:
                    return web.json_response({"ok": False, "error": str(e)}, status=400)

            def _ensure_local_owner_request(request, action: str):
                remote = (request.remote or "").strip()
                if remote not in {"127.0.0.1", "::1", "localhost", ""}:
                    raise PermissionError("Updater nur lokal erlaubt")
                get_gate().require("modify_config", steffen_ctx(f"Dashboard {action} lokales Patch/Update"))

            async def updater_apply(request):
                data = await _request_json(request)
                package_name = (data.get("package") or "").strip()
                restart_after = bool(data.get("restart_after", True))
                if not package_name:
                    return web.json_response({"ok": False, "error": "package fehlt"}, status=400)
                try:
                    _ensure_local_owner_request(request, "apply")
                    result = apply_package(package_name)
                    if restart_after and result.get("ok"):
                        asyncio.create_task(schedule_process_restart())
                    return web.json_response({**result, "restart_scheduled": restart_after and result.get("ok")})
                except PermissionError as e:
                    return web.json_response({"ok": False, "error": str(e)}, status=403)
                except Exception as e:
                    return web.json_response({"ok": False, "error": str(e)}, status=400)

            async def updater_rollback(request):
                data = await _request_json(request)
                restart_after = bool(data.get("restart_after", True))
                try:
                    _ensure_local_owner_request(request, "rollback")
                    result = rollback_last_backup()
                    if restart_after and result.get("ok"):
                        asyncio.create_task(schedule_process_restart())
                    return web.json_response({**result, "restart_scheduled": restart_after and result.get("ok")})
                except PermissionError as e:
                    return web.json_response({"ok": False, "error": str(e)}, status=403)
                except Exception as e:
                    return web.json_response({"ok": False, "error": str(e)}, status=400)

            async def updater_status_api(request):
                return web.json_response(updater_status())

            async def monitor_state(request):
                mon = get_monitor()
                return web.json_response({
                    'ok': True,
                    'state': mon._build_state() if hasattr(mon, '_build_state') else {},
                    'tasks': get_executor().all_tasks(50),
                    'providers': get_relay().provider_status(),
                    'tools': registry.list_tools(),
                    'tool_catalog': list_local_tool_catalog(),
                    'live_tools': await __import__('tool_runtime').list_live_tool_interfaces(),
                    'task_tool_states': get_task_tool_state_store().export_for_tasks([t.get('id') for t in get_executor().all_tasks(50)]),
                    'audit': AuditLog.recent(20),
                })

            app = web.Application()
            app.router.add_get("/", serve)
            app.router.add_get("/monitor_config", monitor_config)
            app.router.add_get("/api/tools", list_tools)
            app.router.add_get("/api/tools/catalog", list_local_catalog)
            app.router.add_get("/api/tools/live", live_tools)
            app.router.add_post("/api/tools/install_local", install_local_tool)
            app.router.add_post("/api/tools/add", add_tool)
            app.router.add_post("/api/tools/update", update_tool)
            app.router.add_post("/api/tools/delete", delete_tool)
            app.router.add_post("/api/tools/toggle", toggle_tool)
            app.router.add_post("/api/tools/suggest", suggest_tool)
            app.router.add_get("/api/mcp/capabilities", mcp_capabilities)
            app.router.add_get("/api/mcp/resources", mcp_resources)
            app.router.add_post("/api/mcp/resource/read", mcp_read_resource)
            app.router.add_get("/api/mcp/prompts", mcp_prompts)
            app.router.add_post("/api/mcp/prompts/get", mcp_get_prompt)
            app.router.add_get("/api/mcp/tools", mcp_tools)
            app.router.add_post("/api/mcp/tools/invoke", mcp_invoke_tool)
            app.router.add_get("/api/update/packages", updater_packages)
            app.router.add_post("/api/update/inspect", updater_inspect)
            app.router.add_post("/api/update/apply", updater_apply)
            app.router.add_post("/api/update/rollback", updater_rollback)
            app.router.add_get("/api/update/status", updater_status_api)
            app.router.add_get("/api/monitor/state", monitor_state)
            runner = web.AppRunner(app)
            await runner.setup()

            last_error = None
            for offset in range(0, 10):
                port = self.port + offset
                try:
                    await web.TCPSite(runner, "localhost", port).start()
                    self.bound_port = port
                    if offset:
                        log.warning(f"Dashboard-Port {self.port} belegt → Fallback auf {port}")
                    log.info(f"Dashboard: http://localhost:{port}")
                    return
                except OSError as e:
                    last_error = e
                    if e.errno == 98 or "address already in use" in str(e).lower():
                        continue
                    raise
            raise last_error or RuntimeError("Kein freier Dashboard-Port gefunden")
        except ImportError:
            log.warning("aiohttp nicht installiert — kein HTTP-Dashboard")
        except Exception as e:
            log.warning(f"Dashboard HTTP-Start: {e}")


_monitor: Optional[MonitorServer] = None

def get_monitor() -> MonitorServer:
    global _monitor
    if _monitor is None:
        _monitor = MonitorServer()
    return _monitor


_dashboard: Optional[DashboardHTTPServer] = None

def get_dashboard() -> DashboardHTTPServer:
    global _dashboard
    if _dashboard is None:
        _dashboard = DashboardHTTPServer()
    return _dashboard

async def _main():
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)-7s %(name)s – %(message)s',
        datefmt='%H:%M:%S'
    )

    mon = get_monitor()
    dash = get_dashboard()

    await dash.start()
    await mon.start()

if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("Monitor gestoppt.")
