"""Phase 1 — native RepoMap (stdlib-ast) unit + kernel integration tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("ISAAC_DISABLE_VECTOR_MEMORY", "1")
os.environ["ISAAC_REPO_MAP"] = "1"

from decision_trace import DecisionTrace, TracePhase
from isaac_core import IsaacKernel, Intent
from memory import Memory, RetrievalContext
from repo_map import (
    extract_mentioned_paths,
    extract_python_tags,
    format_code_map_section,
    get_ranked_context,
    maybe_enrich_retrieval_with_repo_map,
    repo_map_enabled,
)


def _write_fixture(root: Path) -> None:
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "checkout.py").write_text(
        '''
class Cart:
    def add_item(self, sku: str, qty: int) -> None:
        pass

    def total(self) -> float:
        return 0.0


def process_payment(order_id: str, amount: float) -> bool:
    """Charge the customer."""
    return True


def _internal_helper():
    return 1
'''.lstrip(),
        encoding="utf-8",
    )
    (root / "pkg" / "marketing.py").write_text(
        '''
def render_banner(title: str) -> str:
    return title
'''.lstrip(),
        encoding="utf-8",
    )
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_checkout.py").write_text(
        '''
def test_process_payment():
    assert True
'''.lstrip(),
        encoding="utf-8",
    )


class TestRepoMapPhase11(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _write_fixture(self.root)
        os.environ["ISAAC_REPO_MAP"] = "1"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_extract_python_tags_finds_class_and_functions(self) -> None:
        path = self.root / "pkg" / "checkout.py"
        tags = extract_python_tags(path, "pkg/checkout.py")
        names = {t.name for t in tags}
        self.assertIn("Cart", names)
        self.assertIn("process_payment", names)
        self.assertIn("add_item", names)
        kinds = {t.name: t.kind for t in tags}
        self.assertEqual(kinds["Cart"], "class")
        self.assertEqual(kinds["process_payment"], "function")
        self.assertEqual(kinds["add_item"], "method")

    def test_ranked_context_prefers_task_relevant_file(self) -> None:
        ranked = get_ranked_context(
            "fix the bug in process_payment checkout flow",
            max_tokens=400,
            root=self.root,
        )
        self.assertTrue(ranked.enabled)
        self.assertEqual(ranked.backend, "stdlib_ast")
        self.assertGreater(ranked.n_symbols, 0)
        self.assertIn("pkg/checkout.py", ranked.files)
        self.assertIn("process_payment", ranked.text)
        # Marketing should rank lower / often omitted under tight budget
        self.assertLessEqual(ranked.token_estimate, 400)

    def test_extract_mentioned_paths_and_boost(self) -> None:
        paths = extract_mentioned_paths(
            "Bitte fix in pkg/marketing.py und lies pkg/checkout.py"
        )
        self.assertIn("pkg/marketing.py", paths)
        self.assertIn("pkg/checkout.py", paths)
        # Mention-only boost should surface marketing even without payment terms
        ranked = get_ranked_context(
            "kleine Anpassung",
            max_tokens=300,
            root=self.root,
            mentioned=["pkg/marketing.py"],
        )
        self.assertIn("pkg/marketing.py", ranked.files)
        # Enrich auto-extracts mentions from user_input
        ctx = maybe_enrich_retrieval_with_repo_map(
            {},
            user_input="edit pkg/marketing.py render_banner",
            intent="code",
            root=self.root,
        )
        self.assertIn("code_map", ctx)
        self.assertIn("pkg/marketing.py", ctx.get("code_map_meta", {}).get("mentioned") or [])

    def test_disabled_returns_empty(self) -> None:
        os.environ["ISAAC_REPO_MAP"] = "0"
        self.assertFalse(repo_map_enabled())
        ranked = get_ranked_context("process_payment", root=self.root)
        self.assertFalse(ranked.enabled)
        self.assertEqual(ranked.text, "")
        self.assertEqual(ranked.backend, "disabled")

    def test_enrich_retrieval_only_for_code_intent(self) -> None:
        base = {"query": "x", "relevant_facts": []}
        chat_ctx = maybe_enrich_retrieval_with_repo_map(
            base, user_input="process_payment", intent="chat", root=self.root
        )
        self.assertNotIn("code_map", chat_ctx)

        trace = DecisionTrace()
        code_ctx = maybe_enrich_retrieval_with_repo_map(
            base,
            user_input="fix process_payment bug",
            intent="code",
            root=self.root,
            decision_trace=trace,
        )
        self.assertIn("code_map", code_ctx)
        self.assertTrue(code_ctx["code_map"])
        self.assertIn("code_map_meta", code_ctx)
        events = [e.event for e in trace.entries if e.phase == TracePhase.RETRIEVAL]
        self.assertIn("repo_map_built", events)

    def test_format_retrieval_includes_code_map_section(self) -> None:
        ranked = get_ranked_context(
            "process_payment", max_tokens=300, root=self.root
        )
        data = {
            "relevant_facts": [],
            "code_map": ranked.text,
            "code_map_meta": ranked.as_dict(),
        }
        block = format_code_map_section(data)
        self.assertIn("[code_map]", block)
        mem = object.__new__(Memory)
        text = Memory.format_retrieval_context(mem, data)
        self.assertIn("[code_map]", text)
        self.assertIn("process_payment", text)


class TestNativeCodingRoutingPhase4(unittest.TestCase):
    """Phase 4 — free-form repo coding → Intent.CODE; conceptual chat stays CHAT."""

    def setUp(self) -> None:
        self.kernel = object.__new__(IsaacKernel)

    def test_path_plus_fix_maps_to_code(self) -> None:
        from low_complexity import classify_interaction_result
        from isaac_core import detect_intent

        text = "Fix process_payment in pkg/checkout.py"
        c = classify_interaction_result(text)
        intent = self.kernel._resolve_intent_from_classification(
            text, detect_intent(text), c.interaction_class
        )
        self.assertEqual(intent, Intent.CODE)
        strat = self.kernel._select_response_strategy(
            user_input=text,
            intent=intent,
            interaction_class=c.interaction_class,
            retrieval_ctx={},
        )
        self.assertTrue(strat.allow_tools)

    def test_literature_weather_stays_chat_no_tools(self) -> None:
        from low_complexity import classify_interaction_result
        from isaac_core import detect_intent

        text = "Erkläre mir das Wetter als sprachliches Motiv in Literatur"
        c = classify_interaction_result(text)
        intent = self.kernel._resolve_intent_from_classification(
            text, detect_intent(text), c.interaction_class
        )
        self.assertEqual(intent, Intent.CHAT)
        strat = self.kernel._select_response_strategy(
            user_input=text,
            intent=intent,
            interaction_class=c.interaction_class,
            retrieval_ctx={},
        )
        self.assertFalse(strat.allow_tools)


class TestRepoMapKernelIntegration(unittest.TestCase):
    """Phase 1.7 — CODE retrieval gets map; CHAT does not."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _write_fixture(self.root)
        os.environ["ISAAC_REPO_MAP"] = "1"
        os.environ["ISAAC_REPO_MAP_ROOT"] = str(self.root)
        self.kernel = object.__new__(IsaacKernel)
        empty = RetrievalContext(
            query="q",
            active_directives=[],
            relevant_facts=[],
            semantic_context="",
            conversation_history=[],
            relevant_task_results=[],
            preferences_context=[],
            project_context=[],
            behavioral_risks=[],
            relevant_reflections=[],
            open_questions=[],
            relevant_procedures=[],
            active_goals=[],
        )
        self.kernel.memory = SimpleNamespace(
            build_retrieval_context=lambda **kwargs: empty,
        )

    def tearDown(self) -> None:
        os.environ.pop("ISAAC_REPO_MAP_ROOT", None)
        self._tmpdir.cleanup()

    def test_code_intent_enriches_retrieval_with_repo_map(self) -> None:
        with patch(
            "self_model_hooks.enrich_retrieval_with_self_model",
            side_effect=lambda ctx, **kw: dict(ctx),
        ):
            ctx = self.kernel._retrieve_relevant_context(
                user_input="fix process_payment bug in checkout",
                intent=Intent.CODE,
                interaction_class="NORMAL_CHAT",
            )
        self.assertIn("code_map", ctx)
        self.assertTrue(ctx["code_map"])
        self.assertIn("process_payment", ctx["code_map"])
        self.assertIn("code_map_meta", ctx)
        self.assertEqual(ctx["code_map_meta"].get("backend"), "stdlib_ast")

    def test_chat_intent_skips_repo_map(self) -> None:
        with patch(
            "self_model_hooks.enrich_retrieval_with_self_model",
            side_effect=lambda ctx, **kw: dict(ctx),
        ):
            ctx = self.kernel._retrieve_relevant_context(
                user_input="fix process_payment bug in checkout",
                intent=Intent.CHAT,
                interaction_class="NORMAL_CHAT",
            )
        self.assertNotIn("code_map", ctx)

    def test_formatted_prompt_section_for_code(self) -> None:
        with patch(
            "self_model_hooks.enrich_retrieval_with_self_model",
            side_effect=lambda ctx, **kw: dict(ctx),
        ):
            ctx = self.kernel._retrieve_relevant_context(
                user_input="process_payment",
                intent=Intent.CODE,
                interaction_class="NORMAL_CHAT",
            )
        mem = object.__new__(Memory)
        text = Memory.format_retrieval_context(mem, ctx)
        self.assertIn("[code_map]", text)


if __name__ == "__main__":
    unittest.main()
