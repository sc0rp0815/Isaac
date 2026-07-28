"""Regression: fake browser theater, owner confirm, pending mission, timeouts."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestFakeBrowserClaims(unittest.TestCase):
    def test_future_browser_start_is_fake(self):
        from execution_contract import looks_like_fake_tool_success

        self.assertTrue(
            looks_like_fake_tool_success(
                "Ich starte die Browser‑Automation, melde mich an und hole die Revolut‑API‑Keys."
            )
        )
        self.assertTrue(
            looks_like_fake_tool_success(
                "Ich habe mich erfolgreich bei Google eingeloggt."
            )
        )
        self.assertFalse(
            looks_like_fake_tool_success(
                "[Browser] OK\n[Evidence]\nok=true\n"
            )
        )

    def test_anti_hallucination_rewrites_start_claim_and_saves_pending(self):
        from execution_contract import (
            apply_anti_hallucination,
            clear_pending_browser_mission,
            load_pending_browser_mission,
        )

        clear_pending_browser_mission()
        fake = (
            "Ich starte die Browser-Automation, melde mich an und hole die "
            "Revolut-API-Keys. Brauchst du etwas Bestimmtes?"
        )
        out = apply_anti_hallucination(
            "Wann hast du sie?",
            fake,
            tools_ran=False,
        )
        self.assertIn("Execution Contract", out)
        self.assertNotIn("Ich starte die Browser-Automation und hole", out)
        pending = load_pending_browser_mission()
        self.assertIsNotNone(pending)
        self.assertIn("revolut", (pending or {}).get("command", "").lower())
        clear_pending_browser_mission()


class TestOwnerConfirm(unittest.TestCase):
    def test_confirm_phrases(self):
        from execution_contract import is_owner_confirm

        self.assertTrue(is_owner_confirm("Ich bestätige"))
        self.assertTrue(is_owner_confirm("ok mach"))
        self.assertTrue(is_owner_confirm("ja fortfahren"))
        self.assertFalse(is_owner_confirm("Wann hast du sie?"))
        self.assertFalse(is_owner_confirm("bestätige bitte morgen den Termin bei der Bank"))

    def test_pending_roundtrip(self):
        from execution_contract import (
            clear_pending_browser_mission,
            load_pending_browser_mission,
            save_pending_browser_mission,
        )

        clear_pending_browser_mission()
        save_pending_browser_mission(
            "browser: https://example.com extract",
            source="test",
        )
        p = load_pending_browser_mission()
        self.assertIsNotNone(p)
        self.assertIn("example.com", p["command"])
        clear_pending_browser_mission()
        self.assertIsNone(load_pending_browser_mission())


class TestBrowserFlowTimeout(unittest.TestCase):
    def test_run_browser_flow_bounded_timeout(self):
        from isaac_core import IsaacKernel

        k = IsaacKernel.__new__(IsaacKernel)

        async def hang(*_a, **_k):
            await asyncio.sleep(30)
            return {"ok": True}

        browser = MagicMock()
        browser.run_flow = hang

        async def run():
            return await k._run_browser_flow_bounded(
                browser,
                "t1",
                "https://example.com",
                [{"action": "goto", "url": "https://example.com"}],
                timeout_s=0.2,
            )

        result = asyncio.run(run())
        self.assertFalse(result.get("ok"))
        self.assertIn("timeout", (result.get("error") or "").lower())


class TestConfirmResumesPending(unittest.TestCase):
    def test_process_confirm_calls_browser_handler(self):
        from execution_contract import (
            clear_pending_browser_mission,
            save_pending_browser_mission,
        )
        from isaac_core import IsaacKernel, Intent

        clear_pending_browser_mission()
        save_pending_browser_mission(
            "browser: https://example.com",
            source="test",
        )

        k = IsaacKernel.__new__(IsaacKernel)
        k.gate = MagicMock()
        k.gate.is_paused = False
        k.sudo = MagicMock()
        k.sudo.check = MagicMock(return_value=False)
        k._sudo_token = None
        k.cfg = MagicMock()
        k.cfg.browser_automation = True
        k.empathie = MagicMock()
        emp = MagicMock()
        emp.node.zustand = "neutral"
        emp.interface_fehler = None
        k.empathie.analysiere.return_value = emp
        k.ki_dialog = MagicMock()
        k.ki_dialog.als_kontext.return_value = ""
        k.regelwerk = MagicMock()
        k.regelwerk.analysiere.return_value = []
        k.regelwerk.get_pending_frage.return_value = None
        k.regelwerk.get_top_pending_frage.return_value = None
        k._background = None
        k._awaiting_frage_id = None
        k._enforce_constitution_gate = MagicMock(return_value=(None, {}))

        called = {}

        async def fake_browser(text):
            called["text"] = text
            return "[Browser] Navigation OK\n[Evidence]\nok=true"

        k._handle_browser_request = fake_browser
        k._post_process = lambda ui, ant, emp, sc, t0: ant
        k._is_browser_request = MagicMock(return_value=False)
        k._is_agent_request = MagicMock(return_value=False)
        k._resolve_intent_from_classification = MagicMock(return_value=Intent.CHAT)

        with patch("isaac_core.detect_intent", return_value=Intent.CHAT), patch(
            "isaac_core.classify_interaction_result"
        ) as cir, patch("isaac_core.AuditLog"):
            cir.return_value = MagicMock(
                interaction_class="AMBIGUOUS_SHORT",
                word_count=2,
            )
            # process is async
            out = asyncio.run(k.process("Ich bestätige"))

        self.assertIn("example.com", called.get("text", ""))
        self.assertIn("[Browser]", out)
        clear_pending_browser_mission()


if __name__ == "__main__":
    unittest.main()
