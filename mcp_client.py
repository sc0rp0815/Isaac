from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

import aiohttp


class MCPClient:
    def __init__(self, base_url: str, *, prefer_jsonrpc: bool = True):
        base_url = (base_url or "").rstrip("/")
        self.base_url = base_url
        if self.base_url.endswith("/api/mcp"):
            self.api_base = self.base_url
        else:
            self.api_base = self.base_url + "/api/mcp"
        self.jsonrpc_url = f"{self.api_base}/jsonrpc"
        self.prefer_jsonrpc = prefer_jsonrpc
        self._transport: str | None = None
        self._rpc_id = 0
        self._session: aiohttp.ClientSession | None = None
        self._initialized = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def __aenter__(self):
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    @property
    def transport(self) -> str:
        return self._transport or "rest"

    async def _next_rpc_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    async def notify(self, method: str, params: Dict[str, Any] | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        try:
            sess = await self._get_session()
            async with sess.post(self.jsonrpc_url, json=payload):
                return
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return

    async def rpc(
        self,
        method: str,
        params: Dict[str, Any] | None = None,
        req_id: int | None = None,
    ) -> Dict[str, Any]:
        req_id = req_id if req_id is not None else await self._next_rpc_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                sess = await self._get_session()
                async with sess.post(self.jsonrpc_url, json=payload) as res:
                    data = await self._parse_response(res)
                    if data.get("error"):
                        return {
                            "ok": False,
                            "status_code": res.status,
                            "error": data["error"].get("message", "jsonrpc error"),
                            "jsonrpc": data,
                        }
                    return {
                        "ok": True,
                        "status_code": res.status,
                        "result": data.get("result", {}),
                        "jsonrpc": data,
                    }
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.2)
                    continue
                break
        return {
            "ok": False,
            "status_code": 503,
            "error": f"mcp_jsonrpc_failed:{last_error.__class__.__name__ if last_error else 'unknown'}",
        }

    async def ensure_jsonrpc(self) -> bool:
        if self._transport == "jsonrpc" and self._initialized:
            return True
        if not self.prefer_jsonrpc:
            self._transport = "rest"
            return False
        init = await self.rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "isaac-mcp-client", "version": "1.0"},
            },
        )
        if init.get("ok"):
            self._transport = "jsonrpc"
            self._initialized = True
            await self.notify("notifications/initialized")
            return True
        self._transport = "rest"
        return False

    async def _get(self, path: str) -> Dict[str, Any]:
        return await self._request("get", path)

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("post", path, payload)

    async def _request(
        self,
        method: str,
        path: str,
        payload: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                sess = await self._get_session()
                url = f"{self.api_base}{path}"
                if method == "get":
                    async with sess.get(url) as res:
                        return await self._parse_response(res)
                async with sess.post(url, json=payload or {}) as res:
                    return await self._parse_response(res)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.2)
                    continue
                break
        return {
            "ok": False,
            "status_code": 503,
            "error": f"mcp_request_failed:{last_error.__class__.__name__ if last_error else 'unknown'}",
        }

    async def _parse_response(self, res: aiohttp.ClientResponse) -> Dict[str, Any]:
        try:
            data = await res.json(content_type=None)
            if isinstance(data, dict):
                data.setdefault("status_code", res.status)
                return data
            return {"ok": res.status < 400, "status_code": res.status, "data": data}
        except (aiohttp.ContentTypeError, ValueError):
            text = await res.text()
            return {"ok": res.status < 400, "status_code": res.status, "content": text[:2000]}

    async def capabilities(self) -> Dict[str, Any]:
        if await self.ensure_jsonrpc():
            tools = (await self.rpc("tools/list")).get("result", {})
            resources = (await self.rpc("resources/list")).get("result", {})
            prompts = (await self.rpc("prompts/list")).get("result", {})
            return {
                "ok": True,
                "transport": "jsonrpc",
                "capabilities": {
                    "server": {"name": "isaac", "version": "5.3"},
                    "protocolVersion": "2024-11-05",
                    "tools": [t.get("name") for t in tools.get("tools", [])],
                    "resources": [r.get("uri") for r in resources.get("resources", [])],
                    "prompts": [p.get("name") for p in prompts.get("prompts", [])],
                },
            }
        data = await self._get("/capabilities")
        if isinstance(data, dict):
            data["transport"] = "rest"
        return data

    async def resources(self) -> Dict[str, Any]:
        if await self.ensure_jsonrpc():
            result = await self.rpc("resources/list")
            return {"ok": result.get("ok"), "resources": result.get("result", {}).get("resources", [])}
        return await self._get("/resources")

    async def read_resource(
        self,
        uri: str,
        params: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if await self.ensure_jsonrpc():
            result = await self.rpc("resources/read", {"uri": uri, "params": params or {}})
            if not result.get("ok"):
                return result
            contents = result.get("result", {}).get("contents", [])
            resource = None
            if contents:
                text = contents[0].get("text", "")
                try:
                    resource = json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    resource = text
            return {"ok": True, "uri": uri, "resource": resource, "transport": "jsonrpc"}
        return await self._post("/resource/read", {"uri": uri, "params": params or {}})

    async def prompts(self) -> Dict[str, Any]:
        if await self.ensure_jsonrpc():
            result = await self.rpc("prompts/list")
            return {"ok": result.get("ok"), "prompts": result.get("result", {}).get("prompts", [])}
        return await self._get("/prompts")

    async def get_prompt(
        self,
        name: str,
        arguments: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if await self.ensure_jsonrpc():
            result = await self.rpc("prompts/get", {"name": name, "arguments": arguments or {}})
            if not result.get("ok"):
                return result
            messages = result.get("result", {}).get("messages", [])
            prompt = ""
            if messages:
                content = messages[0].get("content", {})
                prompt = content.get("text", "") if isinstance(content, dict) else str(content)
            return {"ok": True, "name": name, "prompt": prompt, "transport": "jsonrpc"}
        return await self._post("/prompts/get", {"name": name, "arguments": arguments or {}})

    async def tools(self) -> Dict[str, Any]:
        if await self.ensure_jsonrpc():
            result = await self.rpc("tools/list")
            return {"ok": result.get("ok"), "tools": result.get("result", {}).get("tools", [])}
        return await self._get("/tools")

    async def invoke_tool(
        self,
        name: str,
        arguments: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if await self.ensure_jsonrpc():
            result = await self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
            if not result.get("ok"):
                return result
            mcp_result = result.get("result", {})
            content = mcp_result.get("content", [])
            text = ""
            if content:
                text = content[0].get("text", "")
            try:
                output = json.loads(text) if text else {}
            except (json.JSONDecodeError, TypeError):
                output = text
            return {
                "ok": not mcp_result.get("isError"),
                "output": output,
                "content": content,
                "transport": "jsonrpc",
                "metadata": {"tool": name},
            }
        return await self._post("/tools/invoke", {"name": name, "arguments": arguments or {}})