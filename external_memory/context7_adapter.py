"""Optional Context7 docs adapter — explicit library documentation lookup.

REST only (no SDK). Explicit owner prefixes: ``docs:`` / ``context7:`` / ``ctx7:``.
Never replaces search.py, memory.py, or opportunistic tool routing.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from external_memory.config import ExternalMemoryConfig

log = logging.getLogger("Isaac.ExternalMemory.Context7")

_DEFAULT_BASE = "https://context7.com"


class Context7Adapter:
    name = "context7"

    def __init__(self, cfg: ExternalMemoryConfig):
        self._cfg = cfg

    def available(self) -> bool:
        if not self._cfg.context7_enabled:
            return False
        return bool(self._api_key())

    def _api_key(self) -> str:
        return (
            getattr(self._cfg, "context7_api_key", None)
            or os.getenv("CONTEXT7_API_KEY")
            or os.getenv("ISAAC_CONTEXT7_API_KEY")
            or ""
        ).strip()

    def _base(self) -> str:
        return (
            getattr(self._cfg, "context7_base_url", None)
            or os.getenv("CONTEXT7_BASE_URL")
            or os.getenv("ISAAC_CONTEXT7_BASE_URL")
            or _DEFAULT_BASE
        ).strip().rstrip("/") or _DEFAULT_BASE

    def _timeout(self) -> float:
        try:
            return max(3.0, min(60.0, float(self._cfg.context7_timeout_s)))
        except (TypeError, ValueError):
            return 20.0

    def _max_snippets(self) -> int:
        try:
            return max(1, min(12, int(self._cfg.context7_max_snippets)))
        except (TypeError, ValueError):
            return 6

    def _headers(self) -> dict[str, str]:
        key = self._api_key()
        return {
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "Isaac-Context7/1.0",
        }

    def _get_json(self, path: str, params: dict[str, str]) -> tuple[Optional[Any], str]:
        if not self.available():
            return None, "Context7 deaktiviert oder CONTEXT7_API_KEY fehlt"
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None and str(v) != ""})
        url = f"{self._base()}{path}"
        if qs:
            url = f"{url}?{qs}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout()) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw.strip():
                    return {}, ""
                return json.loads(raw), ""
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:400]
            return None, f"HTTP {exc.code}: {body}"
        except Exception as exc:
            return None, str(exc)[:200]

    def search_libraries(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Find libraries by name/query. Fail-soft: []."""
        q = (query or "").strip()
        if not q:
            return []
        data, err = self._get_json(
            "/api/v2/libs/search",
            {"query": q, "libraryName": q.split()[0] if q else q},
        )
        if err or not isinstance(data, dict):
            if err:
                log.debug("context7 search failed: %s", err)
            return []
        results = data.get("results") or data.get("libraries") or []
        out: list[dict[str, Any]] = []
        for item in results[: max(1, min(12, limit))]:
            if not isinstance(item, dict):
                continue
            lib_id = (item.get("id") or item.get("libraryId") or "").strip()
            if not lib_id:
                continue
            out.append(
                {
                    "id": lib_id,
                    "title": (item.get("title") or item.get("name") or lib_id).strip(),
                    "description": (item.get("description") or "")[:400],
                    "source": "context7",
                }
            )
        return out

    def get_context(
        self,
        library_id: str,
        query: str,
        *,
        max_snippets: int | None = None,
    ) -> dict[str, Any]:
        """Fetch documentation snippets for a libraryId + query."""
        lib = (library_id or "").strip()
        q = (query or "").strip() or "overview"
        if not lib:
            return {"ok": False, "error": "libraryId fehlt", "text": ""}
        if not lib.startswith("/"):
            lib = "/" + lib.lstrip("/")
        lim = max_snippets if max_snippets is not None else self._max_snippets()
        data, err = self._get_json(
            "/api/v2/context",
            {"libraryId": lib, "query": q, "type": "json"},
        )
        if err:
            # markdown fallback (some paths return text)
            data_md, err_md = self._get_json(
                "/api/v2/context",
                {"libraryId": lib, "query": q},
            )
            if err_md:
                return {"ok": False, "error": err or err_md, "text": "", "library_id": lib}
            if isinstance(data_md, str):
                return {
                    "ok": True,
                    "library_id": lib,
                    "query": q,
                    "text": data_md[:6000],
                    "code_snippets": [],
                    "info_snippets": [],
                }
            data = data_md
        if not isinstance(data, dict):
            return {
                "ok": True,
                "library_id": lib,
                "query": q,
                "text": str(data)[:6000],
                "code_snippets": [],
                "info_snippets": [],
            }
        code = list(data.get("codeSnippets") or [])[:lim]
        info = list(data.get("infoSnippets") or [])[: max(1, lim // 2)]
        text = self._format_context(lib, q, code, info)
        return {
            "ok": True,
            "library_id": lib,
            "query": q,
            "text": text,
            "code_snippets": code,
            "info_snippets": info,
        }

    def _format_context(
        self,
        library_id: str,
        query: str,
        code: list[dict[str, Any]],
        info: list[dict[str, Any]],
    ) -> str:
        lines = [f"Library: {library_id}", f"Query: {query}", ""]
        for sn in code:
            title = (sn.get("codeTitle") or sn.get("pageTitle") or "Snippet").strip()
            desc = (sn.get("codeDescription") or "").strip()
            lang = (sn.get("codeLanguage") or "").strip()
            lines.append(f"### {title}")
            if desc:
                lines.append(desc[:500])
            for block in (sn.get("codeList") or [])[:2]:
                if not isinstance(block, dict):
                    continue
                code_txt = (block.get("code") or "").strip()
                if not code_txt:
                    continue
                fence = lang or block.get("language") or ""
                lines.append(f"```{fence}".rstrip())
                lines.append(code_txt[:1500])
                lines.append("```")
            lines.append("")
        for sn in info:
            content = (sn.get("content") or "").strip()
            if not content:
                continue
            crumb = sn.get("breadcrumb") or ""
            if crumb:
                lines.append(f"### Info ({crumb})")
            else:
                lines.append("### Info")
            lines.append(content[:1200])
            lines.append("")
        body = "\n".join(lines).strip()
        return body[:7000] if body else "(keine Snippets)"

    @staticmethod
    def parse_query(text: str) -> tuple[Optional[str], str, str]:
        """Parse owner prompt into (library_id|None, library_hint, topic_query).

        Formats:
          /vercel/next.js app router
          fastapi | APIRouter prefix
          next.js :: middleware
          fastapi routing  → hint=fastapi, query=full text
        """
        t = (text or "").strip()
        if not t:
            return None, "", ""
        if t.startswith("/"):
            parts = t.split(None, 1)
            lib = parts[0].strip()
            topic = parts[1].strip() if len(parts) > 1 else "overview"
            return lib, lib, topic or "overview"
        for sep in ("|", "::"):
            if sep in t:
                left, right = t.split(sep, 1)
                hint = left.strip()
                topic = right.strip() or "overview"
                if hint.startswith("/"):
                    return hint, hint, topic
                return None, hint, topic
        # free text: first token as library hint
        first = t.split()[0]
        return None, first, t

    def lookup(self, text: str) -> dict[str, Any]:
        """Resolve library (if needed) and fetch docs context."""
        if not self.available():
            return {
                "ok": False,
                "error": "Context7 deaktiviert — CONTEXT7_API_KEY + ISAAC_CONTEXT7_ENABLED=1",
                "text": "",
            }
        lib_id, hint, topic = self.parse_query(text)
        resolved_title = ""
        if not lib_id:
            if not hint:
                return {"ok": False, "error": "leere Anfrage", "text": ""}
            matches = self.search_libraries(hint, limit=5)
            if not matches:
                # retry with full topic as search
                matches = self.search_libraries(topic or hint, limit=5)
            if not matches:
                return {
                    "ok": False,
                    "error": f"Keine Library für „{hint}“ gefunden",
                    "text": "",
                    "hint": hint,
                }
            lib_id = matches[0]["id"]
            resolved_title = matches[0].get("title") or ""
        result = self.get_context(lib_id, topic or "overview")
        if resolved_title:
            result["library_title"] = resolved_title
        result["hint"] = hint
        return result

    def status(self) -> dict[str, Any]:
        key = self._api_key()
        return {
            "name": self.name,
            "enabled": self._cfg.context7_enabled,
            "available": self.available(),
            "mode": "api" if key else "off",
            "api_key_set": bool(key),
            "base_url": self._base(),
            "timeout_s": self._timeout(),
            "max_snippets": self._max_snippets(),
            "init_error": "" if key or not self._cfg.context7_enabled else "no CONTEXT7_API_KEY",
        }
