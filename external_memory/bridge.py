"""Facade for optional external memory backends."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from external_memory.cognee_adapter import CogneeAdapter
from external_memory.config import ExternalMemoryConfig, load_external_memory_config
from external_memory.context7_adapter import Context7Adapter
from external_memory.copilot_agent_adapter import CopilotAgentAdapter
from external_memory.grok_agent_adapter import GrokAgentAdapter
from external_memory.letta_adapter import LettaAdapter
from external_memory.mem0_adapter import Mem0Adapter
from external_memory.open_interpreter_adapter import OpenInterpreterAdapter

log = logging.getLogger("Isaac.ExternalMemory")

# Stable sort key for multi-backend merge
_SOURCE_ORDER = {"mem0": 0, "cognee": 1, "letta": 2}


def _normalize_score(raw: Any) -> float:
    """Map adapter scores onto a rough 0–1 range for gating/display."""
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return 0.5
    if score < 0:
        return 0.0
    if score <= 1.0:
        return score
    # Some backends return 0–100 or quality 0–10
    if score <= 10.0:
        return min(1.0, score / 10.0)
    if score <= 100.0:
        return min(1.0, score / 100.0)
    return 1.0


def _clip(text: str, n: int) -> str:
    t = (text or "").strip()
    if len(t) <= n:
        return t
    return t[: max(0, n - 1)].rstrip() + "…"


class ExternalMemoryBridge:
    """Aggregates Mem0 / Cognee / Letta / OI / Grok / Copilot / Context7 with fail-soft semantics."""

    def __init__(self, cfg: ExternalMemoryConfig | None = None):
        self.cfg = cfg or load_external_memory_config()
        self.mem0 = Mem0Adapter(self.cfg)
        self.cognee = CogneeAdapter(self.cfg)
        self.letta = LettaAdapter(self.cfg)
        self.open_interpreter = OpenInterpreterAdapter(self.cfg)
        self.grok_agent = GrokAgentAdapter(self.cfg)
        self.copilot_agent = CopilotAgentAdapter(self.cfg)
        self.context7 = Context7Adapter(self.cfg)
        self._last_search_meta: dict[str, Any] = {}

    def any_enabled(self) -> bool:
        return self.cfg.any_enabled

    def adapters(self) -> list[Any]:
        # Search path only: Mem0/Cognee/Letta context. OI is explicit-run only.
        return [self.mem0, self.cognee, self.letta]

    def search_all(self, query: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Parallel, time-bounded search across enabled adapters. Never raises."""
        meta: dict[str, Any] = {
            "query_len": len(query or ""),
            "timeout_s": self.cfg.search_timeout_s,
            "errors": {},
            "timed_out": False,
            "adapter_hits": {},
        }
        self._last_search_meta = meta

        if not self.any_enabled() or not (query or "").strip():
            return []

        lim = max(1, min(12, int(limit if limit is not None else self.cfg.search_limit)))
        timeout = float(self.cfg.search_timeout_s)
        min_score = float(self.cfg.search_min_score)
        max_chars = int(self.cfg.max_hit_chars)
        hits: list[dict[str, Any]] = []

        def _one(adapter) -> tuple[str, list[dict[str, Any]], str]:
            name = getattr(adapter, "name", "?")
            if not getattr(adapter, "available", lambda: False)():
                # Letta search: files and/or cloud memory when enabled
                if name != "letta" or not self.cfg.letta_enabled:
                    return name, [], "unavailable"
            try:
                raw = list(adapter.search(query, limit=lim) or [])
                return name, raw, ""
            except Exception as exc:
                log.debug("external search %s failed: %s", name, exc)
                return name, [], str(exc)[:160]

        deadline = time.monotonic() + timeout
        # wait=False on shutdown so a hung adapter cannot block the kernel path
        pool = ThreadPoolExecutor(max_workers=3)
        futs: dict[Any, str] = {}
        try:
            futs = {pool.submit(_one, a): getattr(a, "name", "?") for a in self.adapters()}
            try:
                for fut in as_completed(futs, timeout=timeout):
                    if time.monotonic() > deadline:
                        meta["timed_out"] = True
                        break
                    try:
                        remaining = max(0.05, deadline - time.monotonic())
                        name, part, err = fut.result(timeout=remaining)
                        meta["adapter_hits"][name] = len(part)
                        if err:
                            meta["errors"][name] = err
                        hits.extend(part)
                    except Exception as exc:
                        log.debug("external search future failed: %s", exc)
                        meta["errors"][futs.get(fut, "?")] = str(exc)[:160]
            except TimeoutError:
                meta["timed_out"] = True
                log.debug("external search_all overall timeout (%.1fs)", timeout)
            except Exception as exc:
                log.debug("external search_all failed: %s", exc)
                meta["errors"]["_all"] = str(exc)[:160]
        finally:
            for fut in futs:
                if not fut.done():
                    fut.cancel()
            pool.shutdown(wait=False, cancel_futures=True)

        normalized: list[dict[str, Any]] = []
        for h in hits:
            if not isinstance(h, dict):
                continue
            text = _clip(str(h.get("text") or ""), max_chars)
            if not text:
                continue
            score = _normalize_score(h.get("score"))
            if score < min_score:
                continue
            item = dict(h)
            item["text"] = text
            item["score"] = score
            item["source"] = str(h.get("source") or "external")
            # Structured kind for Letta (archival/core/file) if present
            if item["source"] == "letta" and not item.get("kind"):
                item["kind"] = self._infer_letta_kind(text)
            normalized.append(item)

        # Prefer higher score within source order; cap total
        normalized.sort(
            key=lambda h: (
                _SOURCE_ORDER.get(str(h.get("source") or ""), 9),
                -(float(h.get("score") or 0)),
            )
        )
        out = normalized[: lim * 2]
        meta["returned"] = len(out)
        meta["raw_hits"] = len(hits)
        self._last_search_meta = meta
        return out

    @staticmethod
    def _infer_letta_kind(text: str) -> str:
        t = (text or "").lower()
        if "[letta:archival]" in t or t.startswith("[letta:archival]"):
            return "archival"
        if "[letta:core" in t:
            return "core"
        if "[letta:" in t:
            return "file"
        return "memory"

    def remember_turn(
        self,
        user_text: str,
        assistant_text: str,
        *,
        score: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write turn to write-capable adapters when enabled + score gate."""
        result: dict[str, Any] = {"ok": False, "written": [], "skipped": "disabled"}
        if not self.cfg.write_enabled:
            return result
        if float(score) < float(self.cfg.min_score):
            result["skipped"] = f"score {score} < min {self.cfg.min_score}"
            return result
        user_text = (user_text or "").strip()
        assistant_text = (assistant_text or "").strip()
        if not user_text and not assistant_text:
            result["skipped"] = "empty turn"
            return result

        messages = []
        if user_text:
            messages.append({"role": "user", "content": user_text[:2000]})
        if assistant_text:
            messages.append(
                {"role": "assistant", "content": assistant_text[:2000]}
            )
        meta = dict(metadata or {})
        meta.setdefault("score", score)

        written: list[str] = []
        errors: dict[str, str] = {}
        # Mem0 + Cognee + Letta Cloud archival (bounded write path)
        for adapter in (self.mem0, self.cognee, self.letta):
            name = getattr(adapter, "name", "?")
            try:
                # Letta remember does not require CLI; checks cloud+write itself
                if name == "letta":
                    if not self.cfg.letta_enabled:
                        continue
                elif not adapter.available():
                    continue
                ok = adapter.remember(messages, metadata=meta)
                if ok:
                    written.append(name)
                else:
                    errors[name] = "remember returned false"
            except Exception as exc:
                errors[name] = str(exc)[:200]
                log.debug("remember_turn %s: %s", name, exc)

        return {
            "ok": bool(written),
            "written": written,
            "errors": errors,
            "skipped": "" if written else "no backend wrote",
        }

    def format_hits(self, hits: list[dict[str, Any]]) -> str:
        """Human/LLM-facing block for semantic_context."""
        if not hits:
            return ""
        lines = ["[external_memory]"]
        for h in hits:
            src = str(h.get("source") or "?")
            text = (h.get("text") or "").strip()
            if not text:
                continue
            score = h.get("score")
            kind = h.get("kind") or h.get("label") or ""
            # Avoid double-prefix noise if adapter already labeled
            body = text
            if src == "letta":
                tag = f"letta:{kind}" if kind else "letta"
                # Strip redundant [letta:…] wrappers for cleaner context lines
                if body.startswith("[letta:"):
                    close = body.find("]")
                    if close > 0:
                        body = body[close + 1 :].strip()
                score_s = f" score={float(score):.2f}" if score is not None else ""
                lines.append(f"  - ({tag}{score_s}) {body}")
            else:
                if score is not None:
                    lines.append(f"  - ({src} score={float(score):.2f}) {body}")
                else:
                    lines.append(f"  - ({src}) {body}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def hits_as_preferences(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map Mem0 + Letta hits into preferences_context shape for retrieval."""
        prefs: list[dict[str, Any]] = []
        for h in hits:
            src = str(h.get("source") or "")
            if src not in {"mem0", "letta"}:
                continue
            text = (h.get("text") or "").strip()
            if not text:
                continue
            # Prefer clean body for letta
            if src == "letta" and text.startswith("[letta:"):
                close = text.find("]")
                if close > 0:
                    text = text[close + 1 :].strip()
            kind = str(h.get("kind") or "")
            entry: dict[str, Any] = {
                "source": src,
                "text": text[:180],
                "confidence": float(h.get("score") or 0.5),
            }
            if kind:
                entry["kind"] = kind
            prefs.append(entry)
        return prefs[:6]

    def status(self) -> dict[str, Any]:
        return {
            "any_enabled": self.any_enabled(),
            "write_enabled": self.cfg.write_enabled,
            "min_score": self.cfg.min_score,
            "search_timeout_s": self.cfg.search_timeout_s,
            "search_min_score": self.cfg.search_min_score,
            "search_limit": self.cfg.search_limit,
            "last_search": dict(self._last_search_meta or {}),
            "adapters": {
                "mem0": self.mem0.status(),
                "cognee": self.cognee.status(),
                "letta": self.letta.status(),
                "open_interpreter": self.open_interpreter.status(),
                "grok_agent": self.grok_agent.status(),
                "copilot_agent": self.copilot_agent.status(),
                "context7": self.context7.status(),
            },
        }

    def status_text(self) -> str:
        st = self.status()
        lines = [
            f"External Memory │ enabled={st['any_enabled']} "
            f"write={st['write_enabled']} min_score={st['min_score']} "
            f"search_to={st.get('search_timeout_s')}s "
            f"hit_min={st.get('search_min_score')}"
        ]
        for name, info in st["adapters"].items():
            extra = ""
            if info.get("init_error") and not info.get("available"):
                extra += f" err={info.get('init_error')}"
            mode = info.get("mode")
            if mode and mode not in ("off", "pending", ""):
                extra += f" mode={mode}"
            if name == "letta" and info.get("cloud_ok"):
                extra += " cloud=1"
            lines.append(
                f"  {name}: enabled={info.get('enabled')} "
                f"available={info.get('available')}{extra}"
            )
        return "\n".join(lines)


_bridge: ExternalMemoryBridge | None = None


def get_external_memory_bridge(reset: bool = False) -> ExternalMemoryBridge:
    global _bridge
    if reset or _bridge is None:
        _bridge = ExternalMemoryBridge()
    return _bridge


def reset_external_memory_bridge() -> None:
    """Test helper: drop singleton so next get() reloads config."""
    global _bridge
    _bridge = None
