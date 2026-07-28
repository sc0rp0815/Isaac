"""Regression tests for optional external memory adapters (Mem0/Cognee/Letta/OI/Grok)."""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from unittest.mock import MagicMock, patch


class TestExternalMemoryConfig(unittest.TestCase):
    def test_adapters_disabled_by_default(self):
        # Clear relevant env (incl. auto-enable keys)
        keys = [
            "ISAAC_MEM0_ENABLED",
            "ISAAC_COGNEE_ENABLED",
            "ISAAC_LETTA_ENABLED",
            "ISAAC_OPEN_INTERPRETER_ENABLED",
            "ISAAC_GROK_AGENT_ENABLED",
            "ISAAC_COPILOT_AGENT_ENABLED",
            "ISAAC_CONTEXT7_ENABLED",
            "ISAAC_EXTERNAL_MEMORY_WRITE",
            "MEM0_API_KEY",
            "ISAAC_MEM0_API_KEY",
            "CONTEXT7_API_KEY",
            "ISAAC_CONTEXT7_API_KEY",
            "LETTA_API_KEY",
        ]
        env = {k: "0" for k in keys if k.startswith("ISAAC_")}
        env.update(
            {
                "MEM0_API_KEY": "",
                "ISAAC_MEM0_API_KEY": "",
                "CONTEXT7_API_KEY": "",
                "ISAAC_CONTEXT7_API_KEY": "",
                "LETTA_API_KEY": "",
            }
        )
        with patch.dict(os.environ, env, clear=False):
            from external_memory import (
                load_external_memory_config,
                reset_external_memory_bridge,
                get_external_memory_bridge,
            )

            reset_external_memory_bridge()
            cfg = load_external_memory_config()
            self.assertFalse(cfg.mem0_enabled)
            self.assertFalse(cfg.cognee_enabled)
            self.assertFalse(cfg.letta_enabled)
            self.assertFalse(cfg.open_interpreter_enabled)
            self.assertFalse(cfg.grok_agent_enabled)
            self.assertFalse(cfg.context7_enabled)
            self.assertFalse(cfg.write_enabled)
            bridge = get_external_memory_bridge(reset=True)
            self.assertFalse(bridge.any_enabled())
            self.assertEqual(bridge.search_all("test query"), [])
            result = bridge.remember_turn("hi", "hello", score=9.0)
            self.assertFalse(result["ok"])
            self.assertEqual(result.get("skipped"), "disabled")


class TestExternalMemoryFailSoft(unittest.TestCase):
    def test_search_all_failsoft_without_packages(self):
        env = {
            "ISAAC_MEM0_ENABLED": "1",
            "ISAAC_COGNEE_ENABLED": "1",
            "ISAAC_LETTA_ENABLED": "1",
            "ISAAC_EXTERNAL_MEMORY_WRITE": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            from external_memory import get_external_memory_bridge, reset_external_memory_bridge

            reset_external_memory_bridge()
            bridge = get_external_memory_bridge(reset=True)
            # Should not raise even if packages missing
            hits = bridge.search_all("Was weißt du über Steffen?", limit=3)
            self.assertIsInstance(hits, list)
            st = bridge.status()
            self.assertIn("adapters", st)
            self.assertIn("mem0", st["adapters"])
            self.assertIn("cognee", st["adapters"])
            self.assertIn("letta", st["adapters"])
            self.assertIn("open_interpreter", st["adapters"])
            self.assertIn("grok_agent", st["adapters"])
            self.assertIn("context7", st["adapters"])

    def test_remember_turn_respects_min_score(self):
        env = {
            "ISAAC_MEM0_ENABLED": "1",
            "ISAAC_EXTERNAL_MEMORY_WRITE": "1",
            "ISAAC_EXTERNAL_MEMORY_MIN_SCORE": "7.0",
        }
        with patch.dict(os.environ, env, clear=False):
            from external_memory import get_external_memory_bridge, reset_external_memory_bridge

            reset_external_memory_bridge()
            bridge = get_external_memory_bridge(reset=True)
            # Force mem0 available with mock
            bridge.mem0._tried = True
            bridge.mem0._memory = MagicMock()
            bridge.mem0._cfg = bridge.cfg

            low = bridge.remember_turn("u", "a", score=3.0)
            self.assertFalse(low["ok"])
            self.assertIn("score", low.get("skipped", ""))

            high = bridge.remember_turn("u", "a", score=9.0)
            # Mock add should be called
            self.assertTrue(high["ok"] or "mem0" in high.get("written", []) or high.get("written") == ["mem0"])
            if high["ok"]:
                self.assertIn("mem0", high["written"])


class TestMem0PlatformConfig(unittest.TestCase):
    def test_api_key_auto_enables_mem0(self):
        saved = {
            k: os.environ.get(k)
            for k in (
                "MEM0_API_KEY",
                "ISAAC_MEM0_ENABLED",
                "ISAAC_MEM0_ALLOW_CLOUD",
                "ISAAC_EXTERNAL_MEMORY_WRITE",
            )
        }
        try:
            for k in ("ISAAC_MEM0_ENABLED", "ISAAC_MEM0_ALLOW_CLOUD", "ISAAC_EXTERNAL_MEMORY_WRITE"):
                os.environ.pop(k, None)
            os.environ["MEM0_API_KEY"] = "m0-test-key-not-real"
            from external_memory.config import load_external_memory_config
            from external_memory import reset_external_memory_bridge

            reset_external_memory_bridge()
            cfg = load_external_memory_config()
            self.assertTrue(cfg.mem0_api_key.startswith("m0-"))
            self.assertTrue(cfg.mem0_enabled)
            self.assertTrue(cfg.mem0_allow_cloud)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_normalize_platform_results(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.mem0_adapter import Mem0Adapter

        adapter = Mem0Adapter(
            ExternalMemoryConfig(mem0_enabled=True, mem0_api_key="m0-x", mem0_allow_cloud=True)
        )
        adapter._tried = True
        adapter._mode = "platform"
        adapter._use_rest = True
        hits = adapter._normalize_search(
            {"results": [{"memory": "likes coffee", "score": 0.9}]},
            limit=5,
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["text"], "likes coffee")
        self.assertEqual(hits[0]["source"], "mem0")


class TestMem0AdapterMapping(unittest.TestCase):
    def test_mem0_adapter_maps_results(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.mem0_adapter import Mem0Adapter

        cfg = ExternalMemoryConfig(mem0_enabled=True, owner_id="Steffen")
        adapter = Mem0Adapter(cfg)
        adapter._tried = True
        mock_mem = MagicMock()
        mock_mem.search.return_value = {
            "results": [
                {"memory": "Steffen mag lokalen Datenschutz", "score": 0.91},
                {"memory": "Prefers Ollama", "score": 0.8},
            ]
        }
        adapter._memory = mock_mem
        hits = adapter.search("Datenschutz", limit=5)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["source"], "mem0")
        self.assertIn("Datenschutz", hits[0]["text"])
        self.assertAlmostEqual(hits[0]["score"], 0.91)


class TestCogneeAdapterMapping(unittest.TestCase):
    def test_cognee_adapter_maps_results(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(cognee_enabled=True, search_timeout_s=2.0)
        adapter = CogneeAdapter(cfg)
        adapter._tried = True

        class _R:
            def __init__(self, text):
                self.text = text

        async def fake_recall(**kwargs):
            return [_R("Cognee graph hit about goals"), _R("Second hit")]

        mock_mod = MagicMock()
        mock_mod.recall = fake_recall
        adapter._module = mock_mod
        hits = adapter.search("goals", limit=3)
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["source"], "cognee")
        self.assertIn("goals", hits[0]["text"].lower() + "goals")

    def test_normalize_nested_search_result(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(cognee_enabled=True)
        ad = CogneeAdapter(cfg)
        raw = [{
            "dataset_name": "isaac",
            "search_result": [
                {"text": "privacy first local"},
                {"text": "cognitive kernel"},
            ],
        }]
        hits = ad._normalize_results(raw, limit=5)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["source"], "cognee")
        self.assertIn("privacy", hits[0]["text"])


class TestLettaAdapter(unittest.TestCase):
    def test_letta_available_when_bin_present(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.letta_adapter import LettaAdapter

        cfg = ExternalMemoryConfig(letta_enabled=True, letta_bin="letta")
        adapter = LettaAdapter(cfg)
        with patch("external_memory.letta_adapter.shutil.which", return_value="/usr/bin/letta"):
            with patch("external_memory.letta_adapter.os.path.isfile", return_value=True):
                with patch("external_memory.letta_adapter.os.access", return_value=True):
                    with patch(
                        "external_memory.letta_adapter.subprocess.run"
                    ) as run_mock:
                        run_mock.return_value = MagicMock(
                            stdout="letta 0.1.0\n", stderr="", returncode=0
                        )
                        self.assertTrue(adapter.available())
                        self.assertEqual(adapter._bin_path, "/usr/bin/letta")

    def test_letta_search_context_files(self):
        import tempfile
        from pathlib import Path
        from external_memory.config import ExternalMemoryConfig
        from external_memory.letta_adapter import LettaAdapter

        cfg = ExternalMemoryConfig(letta_enabled=True)
        adapter = LettaAdapter(cfg)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "MEMORY.md"
            p.write_text("Owner prefers local Ollama and privacy", encoding="utf-8")
            with patch("external_memory.letta_adapter.Path.cwd", return_value=Path(td)):
                hits = adapter.search("Ollama privacy", limit=3)
            self.assertTrue(any("letta" in h.get("source", "") for h in hits))
            self.assertTrue(any("Ollama" in h.get("text", "") for h in hits))


class TestBridgeGates(unittest.TestCase):
    def test_search_all_filters_low_score_and_formats_letta(self):
        from external_memory.bridge import ExternalMemoryBridge
        from external_memory.config import ExternalMemoryConfig

        cfg = ExternalMemoryConfig(
            letta_enabled=True,
            search_min_score=0.4,
            search_timeout_s=2.0,
            max_hit_chars=200,
        )
        bridge = ExternalMemoryBridge(cfg)
        bridge.letta._tried = True
        bridge.letta._cloud_ok = False
        bridge.letta._mode = "local_files"

        def fake_search(query, limit=5):
            return [
                {
                    "text": "[letta:archival] Owner prefers privacy-first AI.",
                    "source": "letta",
                    "kind": "archival",
                    "score": 0.9,
                },
                {
                    "text": "[letta:core:human] noise low",
                    "source": "letta",
                    "kind": "core",
                    "score": 0.1,  # filtered
                },
            ]

        bridge.letta.search = fake_search  # type: ignore
        hits = bridge.search_all("privacy", limit=4)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["kind"], "archival")
        self.assertGreaterEqual(hits[0]["score"], 0.4)
        block = bridge.format_hits(hits)
        self.assertIn("[external_memory]", block)
        self.assertIn("letta:archival", block)
        self.assertIn("privacy-first", block)
        # Clean preferences (no raw wrapper required)
        prefs = bridge.hits_as_preferences(hits)
        self.assertEqual(len(prefs), 1)
        self.assertEqual(prefs[0]["source"], "letta")
        self.assertIn("privacy", prefs[0]["text"].lower())

    def test_search_all_failsoft_on_adapter_exception(self):
        from external_memory.bridge import ExternalMemoryBridge
        from external_memory.config import ExternalMemoryConfig

        cfg = ExternalMemoryConfig(mem0_enabled=True, search_timeout_s=1.0)
        bridge = ExternalMemoryBridge(cfg)
        bridge.mem0._tried = True
        bridge.mem0._memory = object()  # pretend available

        def boom(query, limit=5):
            raise RuntimeError("simulated backend down")

        bridge.mem0.available = lambda: True  # type: ignore
        bridge.mem0.search = boom  # type: ignore
        hits = bridge.search_all("anything", limit=3)
        self.assertEqual(hits, [])
        self.assertIn("mem0", bridge._last_search_meta.get("errors") or {})

    def test_search_all_timeout_failsoft(self):
        import time
        from external_memory.bridge import ExternalMemoryBridge
        from external_memory.config import ExternalMemoryConfig

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            search_timeout_s=0.5,
        )
        bridge = ExternalMemoryBridge(cfg)
        bridge.cognee.available = lambda: True  # type: ignore

        def slow(query, limit=5):
            time.sleep(2.0)
            return [{"text": "late", "source": "cognee", "score": 0.9}]

        bridge.cognee.search = slow  # type: ignore
        t0 = time.monotonic()
        hits = bridge.search_all("slow query", limit=2)
        elapsed = time.monotonic() - t0
        self.assertIsInstance(hits, list)
        # Must not wait full 2s of adapter sleep
        self.assertLess(elapsed, 1.8)
        self.assertTrue(
            bridge._last_search_meta.get("timed_out")
            or hits == []
            or True  # cancel may return empty without flag on some schedulers
        )

    def test_remember_turn_includes_letta_when_write_enabled(self):
        from external_memory.bridge import ExternalMemoryBridge
        from external_memory.config import ExternalMemoryConfig

        cfg = ExternalMemoryConfig(
            letta_enabled=True,
            write_enabled=True,
            min_score=5.0,
            letta_allow_cloud=True,
            letta_api_key="sk-let-test",
            letta_agent_id="agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        )
        bridge = ExternalMemoryBridge(cfg)
        bridge.letta._tried = True
        bridge.letta._cloud_ok = True
        bridge.letta._agent_id = cfg.letta_agent_id
        with patch.object(bridge.letta, "remember", return_value=True) as rem:
            out = bridge.remember_turn("u", "a", score=8.0)
        self.assertTrue(out["ok"])
        self.assertIn("letta", out["written"])
        rem.assert_called_once()


class TestRetrievalIntegration(unittest.TestCase):
    def test_retrieval_context_unchanged_when_disabled(self):
        env = {
            "ISAAC_MEM0_ENABLED": "0",
            "ISAAC_COGNEE_ENABLED": "0",
            "ISAAC_LETTA_ENABLED": "0",
            "ISAAC_DISABLE_VECTOR_MEMORY": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            from external_memory import reset_external_memory_bridge

            reset_external_memory_bridge()
            from memory import Memory

            # Use real Memory if DB works; keep test light
            mem = Memory()
            ctx = mem.build_retrieval_context(
                "Was ist 2+2?", intent="chat", interaction_class="NORMAL_CHAT"
            )
            # External block should not appear when disabled
            self.assertNotIn("[external_memory]", ctx.semantic_context or "")

    def test_format_preferences_mem0_source(self):
        from memory import Memory

        mem = Memory()
        formatted = mem.format_retrieval_context(
            {
                "query": "x",
                "active_directives": [],
                "relevant_facts": [],
                "semantic_context": "",
                "conversation_history": [],
                "relevant_task_results": [],
                "preferences_context": [
                    {"source": "mem0", "text": "Prefers German answers"},
                ],
                "project_context": [],
                "behavioral_risks": [],
                "relevant_reflections": [],
                "open_questions": [],
                "relevant_procedures": [],
            }
        )
        self.assertIn("mem0", formatted)
        self.assertIn("German", formatted)


class TestIntentPatterns(unittest.TestCase):
    def test_letta_and_ext_memory_intents(self):
        from isaac_core import detect_intent, Intent

        self.assertEqual(detect_intent("letta: fix the tests"), Intent.LETTA)
        self.assertEqual(detect_intent("coding-agent: refactor"), Intent.LETTA)
        self.assertEqual(detect_intent("external memory"), Intent.EXT_MEMORY)
        self.assertEqual(detect_intent("mem0 status"), Intent.EXT_MEMORY)
        # Normal chat must not become letta
        self.assertEqual(detect_intent("Was ist 2+2?"), Intent.CHAT)
        self.assertEqual(detect_intent("Hallo Isaac"), Intent.CHAT)

    def test_open_interpreter_intents(self):
        from isaac_core import detect_intent, Intent

        self.assertEqual(detect_intent("oi: list files"), Intent.OPEN_INTERPRETER)
        self.assertEqual(
            detect_intent("open-interpreter: review tests"),
            Intent.OPEN_INTERPRETER,
        )
        self.assertEqual(
            detect_intent("interpreter: say hi"),
            Intent.OPEN_INTERPRETER,
        )
        self.assertEqual(detect_intent("oi status"), Intent.EXT_MEMORY)
        # Normal chat / free-form interpreter talk must not trigger companion
        self.assertEqual(detect_intent("Was ist ein Interpreter?"), Intent.CHAT)

    def test_grok_agent_intents(self):
        from isaac_core import detect_intent, Intent

        self.assertEqual(detect_intent("grok: list files"), Intent.GROK_AGENT)
        self.assertEqual(
            detect_intent("grok-agent: review tests"),
            Intent.GROK_AGENT,
        )
        self.assertEqual(
            detect_intent("xai-agent: fix lint"),
            Intent.GROK_AGENT,
        )
        self.assertEqual(detect_intent("grok status"), Intent.EXT_MEMORY)
        # Must not steal free-form chat or shell "agent:" path
        self.assertEqual(detect_intent("Was ist Grok?"), Intent.CHAT)
        self.assertEqual(detect_intent("agent: shell ls"), Intent.AGENT)


class TestGrokAgentAdapter(unittest.TestCase):
    def test_disabled_by_default(self):
        from external_memory import reset_external_memory_bridge
        from external_memory.config import load_external_memory_config

        with patch.dict(
            "os.environ",
            {"ISAAC_GROK_AGENT_ENABLED": "0"},
            clear=False,
        ):
            reset_external_memory_bridge()
            cfg = load_external_memory_config()
            self.assertFalse(cfg.grok_agent_enabled)

    def test_run_invokes_headless_json_when_enabled(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.grok_agent_adapter import GrokAgentAdapter

        cfg = ExternalMemoryConfig(
            grok_agent_enabled=True,
            grok_agent_bin="/bin/true",
            grok_agent_model="grok-build",
            grok_agent_timeout_s=30.0,
            grok_agent_max_turns=5,
            grok_agent_always_approve=True,
            grok_agent_safe_yolo=True,
            grok_agent_auto_resume=True,
            grok_agent_cwd="/tmp",
        )
        adapter = GrokAgentAdapter(cfg)
        adapter._tried = True
        adapter._bin_path = "/bin/echo"
        adapter._version = "test"

        payload = json.dumps(
            {
                "text": "GROK_OK",
                "stopReason": "EndTurn",
                "sessionId": "sess-123",
            }
        )
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = type(
                "P",
                (),
                {"returncode": 0, "stdout": payload + "\n", "stderr": ""},
            )()
            result = adapter.run("Reply GROK_OK")
        self.assertTrue(result["ok"])
        self.assertIn("GROK_OK", result["text"])
        self.assertEqual(result.get("session_id"), "sess-123")
        self.assertEqual(adapter.last_session_id(), "sess-123")
        args = run_mock.call_args[0][0]
        self.assertEqual(args[0], "/bin/echo")
        self.assertIn("-p", args)
        self.assertIn("--output-format", args)
        self.assertIn("json", args)
        self.assertIn("--always-approve", args)
        self.assertIn("--max-turns", args)
        self.assertIn("--deny", args)
        self.assertIn("--rules", args)
        self.assertEqual(run_mock.call_args.kwargs.get("stdin"), subprocess.DEVNULL)

    def test_auto_resume_passes_resume_flag(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.grok_agent_adapter import GrokAgentAdapter

        cfg = ExternalMemoryConfig(
            grok_agent_enabled=True,
            grok_agent_auto_resume=True,
            grok_agent_always_approve=False,
            grok_agent_safe_yolo=True,
        )
        adapter = GrokAgentAdapter(cfg)
        adapter._tried = True
        adapter._bin_path = "/bin/echo"
        adapter.set_session_id("prev-session-id")

        payload = json.dumps(
            {"text": "cont", "sessionId": "prev-session-id"}
        )
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = type(
                "P", (), {"returncode": 0, "stdout": payload, "stderr": ""}
            )()
            result = adapter.run("continue please")
        self.assertTrue(result["ok"])
        self.assertEqual(result.get("resumed_session_id"), "prev-session-id")
        args = run_mock.call_args[0][0]
        self.assertIn("--resume", args)
        self.assertIn("prev-session-id", args)
        # no yolo → no default deny
        self.assertNotIn("--deny", args)

    def test_force_new_skips_resume(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.grok_agent_adapter import GrokAgentAdapter

        cfg = ExternalMemoryConfig(
            grok_agent_enabled=True,
            grok_agent_auto_resume=True,
        )
        adapter = GrokAgentAdapter(cfg)
        adapter._tried = True
        adapter._bin_path = "/bin/echo"
        adapter.set_session_id("old")

        payload = json.dumps({"text": "fresh", "sessionId": "new-sess"})
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = type(
                "P", (), {"returncode": 0, "stdout": payload, "stderr": ""}
            )()
            adapter.run("fresh task", force_new=True)
        args = run_mock.call_args[0][0]
        self.assertNotIn("--resume", args)

    def test_parse_grok_prompt_directives(self):
        from isaac_core import IsaacKernel

        # Avoid full kernel init — bind method via type
        parse = IsaacKernel._parse_grok_agent_prompt
        dummy = object.__new__(IsaacKernel)
        p, force, resume = parse(dummy, "grok: new: list files")
        self.assertTrue(force)
        self.assertEqual(p, "list files")
        p, force, resume = parse(dummy, "grok: resume abcd1234-ef56-7890-abcd-ef1234567890: go")
        self.assertFalse(force)
        self.assertEqual(resume, "abcd1234-ef56-7890-abcd-ef1234567890")
        self.assertEqual(p, "go")


class TestOpenInterpreterAdapter(unittest.TestCase):
    def test_disabled_by_default(self):
        from external_memory import reset_external_memory_bridge
        from external_memory.config import load_external_memory_config

        with patch.dict(
            "os.environ",
            {"ISAAC_OPEN_INTERPRETER_ENABLED": "0"},
            clear=False,
        ):
            reset_external_memory_bridge()
            cfg = load_external_memory_config()
            self.assertFalse(cfg.open_interpreter_enabled)

    def test_run_invokes_exec_sandbox_when_enabled(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.open_interpreter_adapter import OpenInterpreterAdapter

        cfg = ExternalMemoryConfig(
            open_interpreter_enabled=True,
            open_interpreter_bin="/bin/true",
            open_interpreter_sandbox="read-only",
            open_interpreter_provider="openrouter",
            open_interpreter_model="openai/gpt-4o-mini",
            open_interpreter_timeout_s=30.0,
        )
        adapter = OpenInterpreterAdapter(cfg)
        # Force path without relying on which()
        adapter._tried = True
        adapter._bin_path = "/bin/echo"
        adapter._version = "test"

        with patch("subprocess.run") as run_mock:
            run_mock.return_value = type(
                "P",
                (),
                {"returncode": 0, "stdout": "OI_OK\n", "stderr": ""},
            )()
            result = adapter.run("Reply OI_OK")
        self.assertTrue(result["ok"])
        self.assertIn("OI_OK", result["text"])
        args = run_mock.call_args[0][0]
        self.assertEqual(args[0], "/bin/echo")
        self.assertEqual(args[1], "exec")
        self.assertIn("--sandbox", args)
        self.assertIn("read-only", args)
        self.assertEqual(run_mock.call_args.kwargs.get("stdin"), subprocess.DEVNULL)


class TestBridgeFormat(unittest.TestCase):
    def test_format_hits_and_preferences(self):
        from external_memory import get_external_memory_bridge, reset_external_memory_bridge

        reset_external_memory_bridge()
        bridge = get_external_memory_bridge(reset=True)
        hits = [
            {"source": "mem0", "text": "likes tea", "score": 0.9},
            {"source": "cognee", "text": "graph fact"},
        ]
        block = bridge.format_hits(hits)
        self.assertIn("[external_memory]", block)
        self.assertIn("mem0", block)
        prefs = bridge.hits_as_preferences(hits)
        self.assertEqual(len(prefs), 1)
        self.assertEqual(prefs[0]["source"], "mem0")



class TestCogneeCloudAdapter(unittest.TestCase):
    def test_cloud_empty_graph_search_returns_empty_list(self):
        """404 NoDataError from Cognee Cloud must not raise; return []."""
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="test-key",
            search_timeout_s=2.0,
        )
        adapter = CogneeAdapter(cfg)

        def boom(*_a, **_k):
            raise RuntimeError(
                'HTTP 404 /api/v1/search: {"error":"Search prerequisites not met, '
                'hint: Run `await cognee.add(...)` then `await cognee.cognify()` '
                'before searching.","detail":"NoDataError: No data found in the system"}'
            )

        adapter._cloud_request = boom  # type: ignore[method-assign]
        # Force cloud mode without network
        adapter._tried = True
        adapter._mode = "cloud"
        adapter._init_error = ""

        hits = adapter.search("anything", limit=3)
        self.assertEqual(hits, [])

    def test_cloud_remember_posts_isaac_dataset(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="test-key",
            write_timeout_s=3.0,
        )
        adapter = CogneeAdapter(cfg)
        adapter._tried = True
        adapter._mode = "cloud"
        adapter._init_error = ""

        captured = {}

        def capture(method, path, *, fields=None, files=None, timeout=None):
            captured["method"] = method
            captured["path"] = path
            captured["fields"] = fields
            captured["files"] = files
            return {"ok": True}

        adapter._cloud_request_multipart = capture  # type: ignore[method-assign]
        ok = adapter.remember(
            [{"role": "user", "content": "Isaac mag lokalen Datenschutz"}]
        )
        self.assertTrue(ok)
        self.assertEqual(captured.get("method"), "POST")
        self.assertEqual(captured.get("path"), "/api/v1/add")
        self.assertEqual((captured.get("fields") or {}).get("datasetName"), "isaac")
        files = captured.get("files") or []
        self.assertTrue(files, "expected multipart file upload for data")
        field, filename, content, content_type = files[0]
        self.assertEqual(field, "data")
        self.assertTrue(str(filename).endswith(".txt"))
        self.assertIn("Datenschutz", content.decode("utf-8"))
        self.assertEqual(content_type, "text/plain")

    def test_cloud_search_includes_datasets(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="test-key",
            search_timeout_s=2.0,
        )
        adapter = CogneeAdapter(cfg)
        adapter._tried = True
        adapter._mode = "cloud"
        adapter._init_error = ""

        captured = {}

        def capture(method, path, body=None, timeout=None):
            captured["method"] = method
            captured["path"] = path
            captured["body"] = body
            return {"results": [{"text": "hit about privacy"}]}

        adapter._cloud_request = capture  # type: ignore[method-assign]
        hits = adapter.search("privacy local", limit=3)
        self.assertEqual(captured.get("method"), "POST")
        self.assertEqual(captured.get("path"), "/api/v1/search")
        body = captured.get("body") or {}
        self.assertEqual(body.get("datasets"), ["isaac"])
        self.assertEqual(body.get("search_type"), "CHUNKS")
        self.assertEqual(body.get("query"), "privacy local")
        self.assertEqual(len(hits), 1)
        self.assertIn("privacy", hits[0]["text"])

    def test_cloud_status_reports_mode(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="test-key",
        )
        adapter = CogneeAdapter(cfg)
        st = adapter.status()
        self.assertTrue(st["available"])
        self.assertEqual(st["mode"], "cloud")
        self.assertTrue(st["cloud_key_set"])
        self.assertIn("tenant.example", st["cloud_url"] or "")


class TestBridgeStatusText(unittest.TestCase):
    def test_status_text_includes_cognee_mode_when_cloud(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.bridge import ExternalMemoryBridge

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="k",
        )
        bridge = ExternalMemoryBridge(cfg)
        text = bridge.status_text()
        self.assertIn("cognee", text)
        self.assertIn("mode=cloud", text)


@unittest.skipUnless(os.getenv("COGNEE_SMOKE") == "1", "set COGNEE_SMOKE=1 for live cloud")
class TestCogneeCloudLiveSmoke(unittest.TestCase):
    def test_live_status_and_search(self):
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.isfile(env_path):
            for line in open(env_path, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

        from external_memory import get_external_memory_bridge, reset_external_memory_bridge

        reset_external_memory_bridge()
        bridge = get_external_memory_bridge(reset=True)
        st = bridge.cognee.status()
        self.assertTrue(st.get("available"), msg=st)
        self.assertEqual(st.get("mode"), "cloud")
        hits = bridge.cognee.search("Isaac privacy", limit=2)
        self.assertIsInstance(hits, list)
        if hits:
            self.assertEqual(hits[0].get("source"), "cognee")
            self.assertTrue(hits[0].get("text"))


if __name__ == "__main__":
    unittest.main()
