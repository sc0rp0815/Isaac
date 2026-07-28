"""Regression tests for Context7 docs adapter (explicit docs: tool)."""

from __future__ import annotations

import json
import os
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError


class TestContext7Config(unittest.TestCase):
    def test_auto_enable_when_key_present(self):
        env = {
            "CONTEXT7_API_KEY": "ctx7sk-test-key-000",
            "ISAAC_CONTEXT7_ENABLED": "1",
        }
        # clear forced off
        with patch.dict(os.environ, env, clear=False):
            # remove disable if set
            os.environ.pop("ISAAC_CONTEXT7_ENABLED", None)
            os.environ["CONTEXT7_API_KEY"] = "ctx7sk-test-key-000"
            from external_memory import (
                load_external_memory_config,
                reset_external_memory_bridge,
            )

            reset_external_memory_bridge()
            cfg = load_external_memory_config()
            self.assertTrue(cfg.context7_enabled)
            self.assertEqual(cfg.context7_api_key, "ctx7sk-test-key-000")

    def test_explicit_disable(self):
        with patch.dict(
            os.environ,
            {
                "CONTEXT7_API_KEY": "ctx7sk-test-key-000",
                "ISAAC_CONTEXT7_ENABLED": "0",
            },
            clear=False,
        ):
            from external_memory import (
                load_external_memory_config,
                reset_external_memory_bridge,
            )

            reset_external_memory_bridge()
            cfg = load_external_memory_config()
            self.assertFalse(cfg.context7_enabled)


class TestContext7ParseAndLookup(unittest.TestCase):
    def test_parse_query_formats(self):
        from external_memory.context7_adapter import Context7Adapter

        lib, hint, topic = Context7Adapter.parse_query("/vercel/next.js middleware")
        self.assertEqual(lib, "/vercel/next.js")
        self.assertEqual(topic, "middleware")

        lib, hint, topic = Context7Adapter.parse_query("fastapi | APIRouter")
        self.assertIsNone(lib)
        self.assertEqual(hint, "fastapi")
        self.assertEqual(topic, "APIRouter")

        lib, hint, topic = Context7Adapter.parse_query("react useState hook")
        self.assertIsNone(lib)
        self.assertEqual(hint, "react")
        self.assertEqual(topic, "react useState hook")

    def test_lookup_resolves_and_fetches(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.context7_adapter import Context7Adapter

        cfg = ExternalMemoryConfig(
            context7_enabled=True,
            context7_api_key="ctx7sk-test",
            context7_base_url="https://context7.com",
            context7_timeout_s=10.0,
            context7_max_snippets=4,
        )
        ad = Context7Adapter(cfg)

        search_payload = {
            "results": [
                {
                    "id": "/websites/fastapi_tiangolo",
                    "title": "FastAPI",
                    "description": "web framework",
                }
            ]
        }
        context_payload = {
            "codeSnippets": [
                {
                    "codeTitle": "Hello route",
                    "codeDescription": "basic path",
                    "codeLanguage": "python",
                    "codeList": [{"code": "from fastapi import FastAPI\napp = FastAPI()"}],
                }
            ],
            "infoSnippets": [{"content": "FastAPI is a modern framework."}],
        }

        def fake_urlopen(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            body = search_payload if "/libs/search" in url else context_payload
            raw = json.dumps(body).encode()
            resp = MagicMock()
            resp.read.return_value = raw
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = ad.lookup("fastapi | Hello route")
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result.get("library_id"), "/websites/fastapi_tiangolo")
        self.assertIn("Hello route", result.get("text") or "")
        self.assertIn("FastAPI", result.get("text") or "")

    def test_available_requires_key(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.context7_adapter import Context7Adapter

        ad = Context7Adapter(
            ExternalMemoryConfig(context7_enabled=True, context7_api_key="")
        )
        self.assertFalse(ad.available())
        ad2 = Context7Adapter(
            ExternalMemoryConfig(context7_enabled=True, context7_api_key="ctx7sk-x")
        )
        self.assertTrue(ad2.available())


class TestContext7Intent(unittest.TestCase):
    def test_detect_docs_prefix(self):
        from isaac_core import Intent, detect_intent

        self.assertEqual(detect_intent("docs: fastapi routing"), Intent.CONTEXT7)
        self.assertEqual(detect_intent("context7: react"), Intent.CONTEXT7)
        self.assertEqual(detect_intent("ctx7: /vercel/next.js app router"), Intent.CONTEXT7)
        # normal chat must not trigger
        self.assertNotEqual(detect_intent("Was ist 2+2?"), Intent.CONTEXT7)
        self.assertNotEqual(
            detect_intent("Erkläre mir docs in der Literatur"), Intent.CONTEXT7
        )

    def test_handler_help_and_mock_lookup(self):
        from isaac_core import IsaacKernel

        k = IsaacKernel.__new__(IsaacKernel)
        k.gate = MagicMock()
        k.gate.authorize.return_value = (True, "ok")

        help_txt = IsaacKernel._handle_context7(k, "docs:")
        self.assertIn("Format", help_txt)
        self.assertIn("CONTEXT7_API_KEY", help_txt)

        mock_bridge = MagicMock()
        mock_bridge.cfg.context7_enabled = True
        mock_bridge.context7.lookup.return_value = {
            "ok": True,
            "library_id": "/websites/fastapi_tiangolo",
            "library_title": "FastAPI",
            "text": "### Hello\ncode",
        }
        with patch(
            "external_memory.get_external_memory_bridge", return_value=mock_bridge
        ):
            out = IsaacKernel._handle_context7(k, "docs: fastapi | Hello")
        self.assertIn("[Context7", out)
        self.assertIn("Hello", out)
        mock_bridge.context7.lookup.assert_called_once()


class TestContext7BridgeStatus(unittest.TestCase):
    def test_status_includes_context7(self):
        with patch.dict(
            os.environ,
            {
                "ISAAC_CONTEXT7_ENABLED": "1",
                "CONTEXT7_API_KEY": "ctx7sk-test",
                "ISAAC_MEM0_ENABLED": "0",
                "ISAAC_LETTA_ENABLED": "0",
                "ISAAC_COGNEE_ENABLED": "0",
            },
            clear=False,
        ):
            from external_memory import (
                get_external_memory_bridge,
                reset_external_memory_bridge,
            )

            reset_external_memory_bridge()
            bridge = get_external_memory_bridge(reset=True)
            st = bridge.status()
            self.assertIn("context7", st["adapters"])
            self.assertTrue(st["adapters"]["context7"]["enabled"])
            text = bridge.status_text()
            self.assertIn("context7", text)


if __name__ == "__main__":
    unittest.main()
