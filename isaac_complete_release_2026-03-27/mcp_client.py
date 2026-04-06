from __future__ import annotations

"""Isaac – MCP Client
Minimaler HTTP-Client für den lokalen oder externen MCP-Bridge-Zugriff.
"""

from typing import Any, Dict
import requests


class MCPClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def capabilities(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/capabilities", timeout=10).json()

    def resources(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/resources", timeout=10).json()

    def read_resource(self, uri: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/resource/read", json={"uri": uri, "params": params or {}}, timeout=15).json()

    def tools(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/tools", timeout=10).json()

    def invoke_tool(self, name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/tools/invoke", json={"name": name, "arguments": arguments or {}}, timeout=20).json()
