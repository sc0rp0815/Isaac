"""
Ein einfacher Browser-Chat-Provider.
Voraussetzung: playwright installiert und passende Selektoren im Tool-Metadata.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Optional

@dataclass
class BrowserChatResult:
    ok: bool
    content: str = ""
    error: str = ""

class BrowserChatProvider:
    def __init__(self):
        self._playwright = None
        self._browser = None

    async def start(self, headless: bool = True):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def ask(self, tool: dict, prompt: str, timeout: int = 45) -> BrowserChatResult:
        if not self._browser:
            await self.start(headless=tool.get("metadata", {}).get("headless", True))
        page = await self._browser.new_page()
        try:
            url = tool.get("website_url") or tool.get("base_url")
            if not url:
                return BrowserChatResult(False, error="Keine Website-URL konfiguriert")
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)

            meta = tool.get("metadata", {}) or {}
            input_selector = meta.get("input_selector")
            submit_selector = meta.get("submit_selector")
            answer_selector = meta.get("answer_selector")

            if not input_selector:
                return BrowserChatResult(False, error="input_selector fehlt")
            await page.wait_for_selector(input_selector, timeout=timeout * 1000)
            await page.fill(input_selector, prompt)

            if submit_selector:
                await page.click(submit_selector)
            else:
                await page.press(input_selector, "Enter")

            if not answer_selector:
                return BrowserChatResult(True, content="Prompt gesendet, aber kein answer_selector konfiguriert.")

            await page.wait_for_selector(answer_selector, timeout=timeout * 1000)
            nodes = await page.locator(answer_selector).all_inner_texts()
            text = "\n".join([n.strip() for n in nodes if n.strip()]).strip()
            return BrowserChatResult(True, content=text or "Leere Antwort")
        except Exception as e:
            return BrowserChatResult(False, error=str(e))
        finally:
            await page.close()
