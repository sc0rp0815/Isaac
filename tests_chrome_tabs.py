"""Unit tests for Chrome tab URL extraction/filter (no live Magisk required)."""

from __future__ import annotations

import unittest
from unittest import mock


class TestChromeTabsFilter(unittest.TestCase):
    def test_extract_and_filter(self):
        from chrome_tabs import extract_urls_from_text, filter_and_dedupe, is_noise_url, redact_url

        blob = """
        junk https://www.google.com/search?q=letta
        https://connectivitycheck.gstatic.com/generate_204
        https://gemini.google.com/
        https://accounts.google.com/o/oauth2/v2/auth?code=SECRET&client_id=x
        https://www.letta.com/
        https://www.letta.com/
        """
        urls = extract_urls_from_text(blob)
        cleaned = filter_and_dedupe(urls, full=False)
        self.assertTrue(any("letta.com" in u for u in cleaned))
        self.assertTrue(any("gemini.google.com" in u for u in cleaned))
        self.assertFalse(any("connectivitycheck" in u for u in cleaned))
        self.assertTrue(is_noise_url("http://connectivitycheck.gstatic.com/generate_204"))
        red = redact_url("https://accounts.google.com/o/oauth2/v2/auth?code=SECRET&foo=1")
        self.assertNotIn("SECRET", red)
        self.assertIn("accounts.google.com", red)

    def test_format_report(self):
        from chrome_tabs import format_tabs_report

        text = format_tabs_report(
            {
                "ok": True,
                "tabs": [
                    {"index": 1, "url": "https://a.example/", "display": "https://a.example/"},
                ],
                "files_scanned": 3,
                "full": False,
            }
        )
        self.assertIn("Chrome Tabs", text)
        self.assertIn("a.example", text)
        self.assertIn("öffne tab", text.lower() or text)


class TestChromeTabsDetect(unittest.TestCase):
    def test_detect(self):
        from owner_action import detect_owner_action

        a = detect_owner_action("chrome tabs")
        self.assertIsNotNone(a)
        self.assertEqual(a.kind, "chrome_tabs")
        a2 = detect_owner_action("öffne tab 2")
        self.assertIsNotNone(a2)
        self.assertEqual(a2.kind, "chrome_tab_open")
        self.assertEqual(a2.params.get("index"), 2)


if __name__ == "__main__":
    unittest.main()
