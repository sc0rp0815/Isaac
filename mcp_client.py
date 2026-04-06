from __future__ import annotations

import aiohttp
from typing import Any, Dict


class MCPClient:
    def __init__(self, base_url: str):
        base_url = (base_url or '').rstrip('/')
        self.base_url = base_url
        if self.base_url.endswith('/api/mcp'):
            self.api_base = self.base_url
        else:
            self.api_base = self.base_url + '/api/mcp'

    async def _get(self, path: str) -> Dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.get(f"{self.api_base}{path}") as res:
                data = await res.json(content_type=None)
                if isinstance(data, dict):
                    data.setdefault("status_code", res.status)
                return data

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.post(f"{self.api_base}{path}", json=payload) as res:
                data = await res.json(content_type=None)
                if isinstance(data, dict):
                    data.setdefault("status_code", res.status)
                return data

    async def capabilities(self) -> Dict[str, Any]:
        return await self._get('/capabilities')

    async def resources(self) -> Dict[str, Any]:
        return await self._get('/resources')

    async def read_resource(self, uri: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return await self._post('/resource/read', {"uri": uri, "params": params or {}})

    async def prompts(self) -> Dict[str, Any]:
        return await self._get('/prompts')

    async def get_prompt(self, name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return await self._post('/prompts/get', {"name": name, "arguments": arguments or {}})

    async def tools(self) -> Dict[str, Any]:
        return await self._get('/tools')

    async def invoke_tool(self, name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return await self._post('/tools/invoke', {"name": name, "arguments": arguments or {}})
