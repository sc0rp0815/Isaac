"""
Isaac – Async Multi-Provider Relay
====================================
Vollständig async. Kein threading.Thread mehr.

Verbesserungen:
  - Circuit Breaker pro Provider
  - robustere Token-Schätzung und TPM-Tracking
  - vollständigerer Cache-Key
  - Ollama-Healthcheck / sanfter Fallback
  - Provider-Status mit Fehlern, Cooldown und Latenz
"""

from __future__ import annotations

import asyncio
import aiohttp
import hashlib
import time
import logging
from dataclasses import dataclass, field
from collections import deque
from typing import Optional

from config  import get_config, ProviderConfig
from audit   import AuditLog

log = logging.getLogger("Isaac.Relay")


class RateLimiter:
    def __init__(self, rpm: int, tpm: int):
        self.rpm = max(1, rpm)
        self.tpm = max(1, tpm)
        self._req_times: deque[float] = deque()
        self._tok_log: deque[tuple[float, int]] = deque()
        self._lock = asyncio.Lock()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 1
        return max(1, len(text) // 4)

    async def acquire(self, tokens: int = 100):
        tokens = max(1, tokens)
        async with self._lock:
            now = time.monotonic()
            window = now - 60.0

            while self._req_times and self._req_times[0] < window:
                self._req_times.popleft()
            while self._tok_log and self._tok_log[0][0] < window:
                self._tok_log.popleft()

            req_count = len(self._req_times)
            token_count = sum(t for _, t in self._tok_log)

            if req_count >= self.rpm:
                wait = max(0.0, 60.5 - (now - self._req_times[0]))
                if wait > 0:
                    await asyncio.sleep(wait)

            if token_count + tokens > self.tpm * 0.9 and self._tok_log:
                wait = max(0.0, 60.5 - (now - self._tok_log[0][0]))
                if wait > 0:
                    await asyncio.sleep(wait)

            ts = time.monotonic()
            self._req_times.append(ts)
            self._tok_log.append((ts, tokens))

    def record_actual(self, estimated: int, actual: int):
        actual = max(1, actual)
        extra = max(0, actual - max(1, estimated))
        if extra:
            self._tok_log.append((time.monotonic(), extra))

    def status(self) -> str:
        now = time.monotonic()
        window = now - 60.0
        req = sum(1 for t in self._req_times if t > window)
        tok = sum(t for ts, t in self._tok_log if ts > window)
        return f"RPM:{req}/{self.rpm} TPM:{tok}/{self.tpm}"


class ResponseCache:
    def __init__(self, ttl: int = 30):
        self.ttl = ttl
        self._c: dict[str, tuple[float, str]] = {}

    def _key(self, prompt: str, system: str, provider: str) -> str:
        payload = f"{provider}\n{system}\n{prompt}".encode("utf-8", errors="replace")
        return hashlib.sha256(payload).hexdigest()

    def get(self, prompt: str, system: str, provider: str) -> Optional[str]:
        k = self._key(prompt, system, provider)
        entry = self._c.get(k)
        if entry and time.time() - entry[0] < self.ttl:
            return entry[1]
        return None

    def set(self, prompt: str, system: str, provider: str, antwort: str):
        self._c[self._key(prompt, system, provider)] = (time.time(), antwort)
        now = time.time()
        self._c = {k: v for k, v in self._c.items() if now - v[0] < self.ttl * 2}


@dataclass
class ProviderHealth:
    consecutive_failures: int = 0
    blacklisted_until: float = 0.0
    last_error: str = ""
    last_success_latency: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    last_ok_ts: float = 0.0

    def available_now(self) -> bool:
        return time.monotonic() >= self.blacklisted_until


class AsyncRelay:
    def __init__(self):
        self.cfg = get_config()
        self.cache = ResponseCache(ttl=self.cfg.relay.cache_ttl)
        self._limiters: dict[str, RateLimiter] = {}
        self._health: dict[str, ProviderHealth] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._setup_limiters()
        log.info(
            "Relay online │ Primär: %s │ Verfügbar: %s",
            self.cfg.relay.primary_provider,
            ", ".join(self.cfg.available_providers),
        )

    def _setup_limiters(self):
        for name, p in self.cfg.providers.items():
            self._limiters[name] = RateLimiter(p.rpm, p.tpm)
            self._health.setdefault(name, ProviderHealth())

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=max(30, self.cfg.relay.max_retries * 30))
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _is_runtime_available(self, prov_cfg: ProviderConfig) -> bool:
        if prov_cfg.name == "ollama":
            return prov_cfg.enabled
        return prov_cfg.available

    def _mark_success(self, name: str, latency: float):
        h = self._health[name]
        h.consecutive_failures = 0
        h.last_error = ""
        h.last_success_latency = latency
        h.success_count += 1
        h.last_ok_ts = time.time()

    def _mark_failure(self, name: str, message: str):
        h = self._health[name]
        h.consecutive_failures += 1
        h.failure_count += 1
        h.last_error = message[:250]
        cooldown = min(180, 10 * h.consecutive_failures)
        if h.consecutive_failures >= 3:
            h.blacklisted_until = time.monotonic() + cooldown

    async def ask(self, prompt: str,
                  system: str = "Du bist Isaac, ein autonomes KI-System.",
                  provider: Optional[str] = None,
                  context: str = "",
                  use_cache: bool = True,
                  tokens: int = 0,
                  task_id: str = "",
                  model_override: Optional[str] = None) -> str:
        prov_name = provider or self.cfg.relay.primary_provider
        prov_cfg = self.cfg.get_provider(prov_name)
        if not prov_cfg:
            return f"[RELAY] Unbekannter Provider: {prov_name}"
        if not self._is_runtime_available(prov_cfg):
            return f"[RELAY-FEHLER:{prov_name}] Provider nicht konfiguriert oder deaktiviert"

        max_c = self.cfg.relay.max_context_chars
        if context and len(context) > max_c:
            half = max_c // 2
            context = f"{context[:half]}\n[...komprimiert...]\n{context[-half:]}"
        full_prompt = f"{context}\n\n{prompt}".strip() if context else prompt

        if use_cache:
            cache_provider = f"{prov_name}:{model_override}" if model_override else prov_name
            cached = self.cache.get(full_prompt, system, cache_provider)
            if cached:
                return cached

        limiter = self._limiters.get(prov_name)
        approx_tokens = tokens or RateLimiter.estimate_tokens(system + "\n" + full_prompt)
        if limiter:
            await limiter.acquire(approx_tokens)

        for versuch in range(1, self.cfg.relay.max_retries + 1):
            try:
                t0 = time.monotonic()
                result, actual_tokens = await self._dispatch(prov_cfg, full_prompt, system, model_override=model_override)
                dauer = round(time.monotonic() - t0, 2)
                self._mark_success(prov_name, dauer)
                if limiter:
                    limiter.record_actual(approx_tokens, actual_tokens)
                AuditLog.action("Relay", f"ask:{prov_name}", f"task={task_id} t={dauer}s", erfolg=True)
                if use_cache:
                    self.cache.set(full_prompt, system, cache_provider, result)
                return result
            except RateLimitErr:
                self._mark_failure(prov_name, "Rate Limit")
                await asyncio.sleep(min(20, 5 * versuch))
            except ProviderErr as e:
                msg = str(e)
                self._mark_failure(prov_name, msg)
                AuditLog.error("Relay", msg, f"provider={prov_name}")
                if versuch == self.cfg.relay.max_retries:
                    return f"[RELAY-FEHLER:{prov_name}] {msg}"
                await asyncio.sleep(min(10, 2 * versuch))

        return f"[RELAY] Alle {self.cfg.relay.max_retries} Versuche fehlgeschlagen"

    async def ask_with_fallback(self, prompt: str, system: str = "",
                                preferred: Optional[str] = None,
                                task_id: str = "",
                                model_override: Optional[str] = None) -> tuple[str, str]:
        reihe: list[str] = []
        if preferred:
            reihe.append(preferred)
        primary = self.cfg.relay.primary_provider
        if primary not in reihe:
            reihe.append(primary)
        for p in self.cfg.available_providers:
            if p not in reihe:
                reihe.append(p)

        usable: list[str] = []
        for name in reihe:
            cfg = self.cfg.get_provider(name)
            if not cfg or not self._is_runtime_available(cfg):
                continue
            if not self._health[name].available_now():
                continue
            usable.append(name)

        if not usable:
            usable = [n for n in reihe if self.cfg.get_provider(n)]

        for pname in usable:
            result = await self.ask(prompt, system, provider=pname, task_id=task_id, model_override=model_override)
            if not result.startswith("[RELAY-FEHLER"):
                return result, pname
            log.warning("Fallback: %s fehlgeschlagen → weiter", pname)

        return "[RELAY] Alle Provider fehlgeschlagen.", "none"

    async def _dispatch(self, cfg: ProviderConfig, prompt: str, system: str, model_override: Optional[str] = None) -> tuple[str, int]:
        handlers = {
            "openai": self._openai_compat,
            "groq": self._openai_compat,
            "mistral": self._openai_compat,
            "together": self._openai_compat,
            "perplexity": self._openai_compat,
            "openrouter": self._openrouter,
            "anthropic": self._anthropic,
            "gemini": self._gemini,
            "cohere": self._cohere,
            "ollama": self._ollama,
            "huggingface": self._huggingface,
        }
        fn = handlers.get(cfg.name)
        if not fn:
            raise ProviderErr(f"Kein Handler: {cfg.name}")
        return await fn(cfg, prompt, system)

    async def _openai_compat(self, cfg: ProviderConfig, prompt: str, system: str, model_override: Optional[str] = None) -> str:
        if not cfg.api_key:
            raise ProviderErr(f"{cfg.name}: API-Key fehlt")
        session = await self._get_session()
        payload = {
            "model": model_override or cfg.default_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": 1200,
            "temperature": 0.3,
        }
        async with session.post(
            cfg.base_url,
            headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=cfg.timeout),
        ) as r:
            if r.status == 429:
                raise RateLimitErr(f"{cfg.name} Rate Limit")
            if r.status != 200:
                txt = await r.text()
                raise ProviderErr(f"{cfg.name} {r.status}: {txt[:120]}")
            data = await r.json()
            content = data["choices"][0]["message"]["content"]
            usage = ((data.get("usage") or {}).get("total_tokens") or RateLimiter.estimate_tokens(content))
            return content, usage

    async def _openrouter(self, cfg: ProviderConfig, prompt: str, system: str, model_override: Optional[str] = None) -> str:
        if not cfg.api_key:
            raise ProviderErr("OpenRouter: API-Key fehlt")
        session = await self._get_session()
        payload = {
            "model": model_override or cfg.default_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": 1200,
            "temperature": 0.3,
        }
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }
        from os import getenv
        referer = getenv("OPENROUTER_HTTP_REFERER", "")
        title = getenv("OPENROUTER_APP_TITLE", "Isaac")
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
        async with session.post(
            cfg.base_url,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=cfg.timeout),
        ) as r:
            if r.status == 429:
                raise RateLimitErr("OpenRouter Rate Limit")
            if r.status != 200:
                txt = await r.text()
                raise ProviderErr(f"OpenRouter {r.status}: {txt[:160]}")
            data = await r.json()
            content = data["choices"][0]["message"]["content"]
            usage = ((data.get("usage") or {}).get("total_tokens") or RateLimiter.estimate_tokens(content))
            return content, usage

    async def _anthropic(self, cfg: ProviderConfig, prompt: str, system: str, model_override: Optional[str] = None) -> str:
        if not cfg.api_key:
            raise ProviderErr("Anthropic: API-Key fehlt")
        session = await self._get_session()
        async with session.post(
            cfg.base_url,
            headers={"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            json={"model": cfg.default_model, "max_tokens": 1200, "system": system, "messages": [{"role": "user", "content": prompt}]},
            timeout=aiohttp.ClientTimeout(total=cfg.timeout),
        ) as r:
            if r.status == 429:
                raise RateLimitErr("Anthropic Rate Limit")
            if r.status != 200:
                txt = await r.text()
                raise ProviderErr(f"Anthropic {r.status}: {txt[:120]}")
            data = await r.json()
            content = data["content"][0]["text"]
            usage = ((data.get("usage") or {}).get("input_tokens", 0) + (data.get("usage") or {}).get("output_tokens", 0) or RateLimiter.estimate_tokens(content))
            return content, usage

    async def _gemini(self, cfg: ProviderConfig, prompt: str, system: str, model_override: Optional[str] = None) -> str:
        if not cfg.api_key:
            raise ProviderErr("Gemini: API-Key fehlt")
        url = f"{cfg.base_url}/{cfg.default_model}:generateContent?key={cfg.api_key}"
        session = await self._get_session()
        async with session.post(
            url,
            json={"contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}], "generationConfig": {"maxOutputTokens": 1200, "temperature": 0.3}},
            timeout=aiohttp.ClientTimeout(total=cfg.timeout),
        ) as r:
            if r.status == 429:
                raise RateLimitErr("Gemini Rate Limit")
            if r.status != 200:
                txt = await r.text()
                raise ProviderErr(f"Gemini {r.status}: {txt[:120]}")
            data = await r.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            usage = (((data.get("usageMetadata") or {}).get("totalTokenCount")) or RateLimiter.estimate_tokens(content))
            return content, usage

    async def _cohere(self, cfg: ProviderConfig, prompt: str, system: str, model_override: Optional[str] = None) -> str:
        if not cfg.api_key:
            raise ProviderErr("Cohere: API-Key fehlt")
        session = await self._get_session()
        async with session.post(
            cfg.base_url,
            headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
            json={"model": cfg.default_model, "preamble": system, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1200, "temperature": 0.3},
            timeout=aiohttp.ClientTimeout(total=cfg.timeout),
        ) as r:
            if r.status == 429:
                raise RateLimitErr("Cohere Rate Limit")
            if r.status != 200:
                txt = await r.text()
                raise ProviderErr(f"Cohere {r.status}: {txt[:120]}")
            data = await r.json()
            try:
                content = data["message"]["content"][0]["text"]
            except (KeyError, IndexError, TypeError):
                content = data.get("text", "[Cohere: leere Antwort]")
            usage = ((((data.get("usage") or {}).get("tokens") or {}).get("output_tokens")) or RateLimiter.estimate_tokens(content))
            return content, usage

    async def _ollama(self, cfg: ProviderConfig, prompt: str, system: str) -> tuple[str, int]:
        session = await self._get_session()
        try:
            tags_url = cfg.base_url.rsplit("/api/chat", 1)[0] + "/api/tags"
            async with session.get(tags_url, timeout=aiohttp.ClientTimeout(total=10)) as tag_resp:
                if tag_resp.status == 200:
                    tag_data = await tag_resp.json()
                    available = {m.get("name", "") for m in tag_data.get("models", [])}
                    if available and cfg.default_model not in available and f"{cfg.default_model}:latest" not in available:
                        raise ProviderErr(f"Ollama-Modell '{cfg.default_model}' nicht installiert")
            async with session.post(
                cfg.base_url,
                json={"model": cfg.default_model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "stream": False, "options": {"temperature": 0.3, "num_predict": 800}},
                timeout=aiohttp.ClientTimeout(total=max(60, cfg.timeout)),
            ) as r:
                txt = await r.text()
                if r.status != 200:
                    raise ProviderErr(f"Ollama {r.status}: {txt[:200]}")
                import json as _json
                data = _json.loads(txt)
                msg = ((data.get("message") or {}).get("content") or "").strip()
                if not msg:
                    raise ProviderErr("Ollama lieferte leere Antwort")
                usage = (data.get("prompt_eval_count", 0) + data.get("eval_count", 0) or RateLimiter.estimate_tokens(msg))
                return msg, usage
        except aiohttp.ClientConnectorError:
            raise ProviderErr("Ollama nicht erreichbar. Starte mit: ollama serve")
        except asyncio.TimeoutError:
            raise ProviderErr("Ollama Timeout")

    async def _huggingface(self, cfg: ProviderConfig, prompt: str, system: str) -> tuple[str, int]:
        if not cfg.api_key:
            raise ProviderErr("HuggingFace: API-Key fehlt")
        url = f"{cfg.base_url}/{cfg.default_model}"
        full = f"{system}\n\nUser: {prompt}\nAssistant:"
        session = await self._get_session()
        async with session.post(
            url,
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={"inputs": full, "parameters": {"max_new_tokens": 800, "temperature": 0.3, "return_full_text": False}},
            timeout=aiohttp.ClientTimeout(total=cfg.timeout),
        ) as r:
            if r.status == 429:
                raise RateLimitErr("HuggingFace Rate Limit")
            if r.status == 503:
                raise ProviderErr("HuggingFace: Modell lädt")
            if r.status != 200:
                txt = await r.text()
                raise ProviderErr(f"HuggingFace {r.status}: {txt[:120]}")
            data = await r.json()
            if isinstance(data, list):
                content = data[0].get("generated_text", "")
            else:
                content = str(data)[:500]
            return content, RateLimiter.estimate_tokens(content)

    def provider_status(self) -> list[dict]:
        status = []
        for name, pcfg in self.cfg.providers.items():
            lim = self._limiters.get(name)
            health = self._health.get(name, ProviderHealth())
            status.append({
                "name": name,
                "available": self._is_runtime_available(pcfg),
                "model": pcfg.default_model,
                "rate": lim.status() if lim else "-",
                "primary": name == self.cfg.relay.primary_provider,
                "enabled": pcfg.enabled,
                "has_api_key": bool(pcfg.api_key),
                "last_error": health.last_error,
                "cooldown": max(0, int(health.blacklisted_until - time.monotonic())),
                "latency": round(health.last_success_latency, 2),
                "success_count": health.success_count,
                "failure_count": health.failure_count,
                "base_url": pcfg.base_url,
                "timeout": pcfg.timeout,
            })
        return status


class RateLimitErr(Exception):
    pass


class ProviderErr(Exception):
    pass


_relay: Optional[AsyncRelay] = None


def get_relay() -> AsyncRelay:
    global _relay
    if _relay is None:
        _relay = AsyncRelay()
    return _relay
