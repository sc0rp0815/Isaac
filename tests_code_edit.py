"""Phase 2 — structured code_edit (SEARCH/REPLACE) unit + executor integration."""

from __future__ import annotations

import asyncio
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("ISAAC_DISABLE_VECTOR_MEMORY", "1")
os.environ["ISAAC_CODE_EDIT"] = "1"

from config import WORKSPACE
from decision_trace import DecisionTrace, TracePhase
from code_edit import (
    EditHunk,
    apply_edit,
    apply_edits,
    plan_edits,
    verify,
)
from executor import Executor, Strategy, Task, TaskStatus, TaskType


SAMPLE_BLOCK = """\
pkg/sample.py
<<<<<<< SEARCH
def greet(name):
    return "hi " + name
=======
def greet(name: str) -> str:
    return f"hello {name}"
>>>>>>> REPLACE
"""


class TestCodeEditPhase21(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(WORKSPACE) / ".isaac_code_edit_test"
        if self.root.exists():
            shutil.rmtree(self.root)
        pkg = self.root / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "sample.py").write_text(
            'def greet(name):\n    return "hi " + name\n',
            encoding="utf-8",
        )
        (pkg / "dup.py").write_text(
            "x = 1\nx = 1\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_plan_edits_parses_search_replace_block(self) -> None:
        plan = plan_edits(SAMPLE_BLOCK)
        self.assertTrue(plan.ok, plan.errors)
        self.assertEqual(len(plan.hunks), 1)
        self.assertEqual(plan.hunks[0].path, "pkg/sample.py")
        self.assertIn("def greet(name):", plan.hunks[0].search)
        self.assertIn("hello", plan.hunks[0].replace)

    def test_plan_edits_rejects_empty(self) -> None:
        plan = plan_edits("just prose, no blocks")
        self.assertFalse(plan.ok)
        self.assertIn("no_search_replace_blocks", plan.errors)

    def test_dry_run_apply_unique_match(self) -> None:
        plan = plan_edits(
            f"""\
pkg/sample.py
<<<<<<< SEARCH
def greet(name):
    return "hi " + name
=======
def greet(name: str) -> str:
    return f"hello {{name}}"
>>>>>>> REPLACE
"""
        )
        # Use path relative to self.root via root=
        hunk = EditHunk(
            path="pkg/sample.py",
            search=plan.hunks[0].search,
            replace=plan.hunks[0].replace,
        )
        res = apply_edit(hunk, dry_run=True, root=self.root)
        self.assertTrue(res.ok, res.message)
        self.assertTrue(res.dry_run)
        self.assertFalse(res.written)
        self.assertIn("hello", res.diff_preview)
        # file unchanged
        text = (self.root / "pkg" / "sample.py").read_text(encoding="utf-8")
        self.assertIn("hi ", text)

    def test_apply_writes_and_verify(self) -> None:
        hunk = EditHunk(
            path="pkg/sample.py",
            search='def greet(name):\n    return "hi " + name\n',
            replace='def greet(name: str) -> str:\n    return f"hello {name}"\n',
        )
        trace = DecisionTrace()
        res = apply_edit(hunk, dry_run=False, root=self.root, decision_trace=trace)
        self.assertTrue(res.ok, res.message)
        self.assertTrue(res.written)
        v = verify(
            "pkg/sample.py",
            root=self.root,
            must_contain=["hello", "str"],
            must_not_contain=["hi "],
            python_syntax=True,
        )
        self.assertTrue(v.ok, v.message)
        events = [e.event for e in trace.entries if e.phase == TracePhase.EXECUTION]
        self.assertIn("code_edit_apply", events)

    def test_ambiguous_search_refused(self) -> None:
        hunk = EditHunk(path="pkg/dup.py", search="x = 1\n", replace="x = 2\n")
        res = apply_edit(hunk, dry_run=True, root=self.root)
        self.assertFalse(res.ok)
        self.assertIn("search_ambiguous", res.message)

    def test_search_not_found(self) -> None:
        hunk = EditHunk(
            path="pkg/sample.py",
            search="def does_not_exist():\n    pass\n",
            replace="def x():\n    pass\n",
        )
        res = apply_edit(hunk, dry_run=True, root=self.root)
        self.assertFalse(res.ok)
        self.assertEqual(res.message, "search_not_found")

    def test_apply_from_model_text_includes_repair_hints(self) -> None:
        from code_edit import apply_from_model_text

        block = (
            "pkg/sample.py\n"
            "<<<<<<< SEARCH\n"
            "def does_not_exist():\n"
            "    pass\n"
            "=======\n"
            "def x():\n"
            "    pass\n"
            ">>>>>>> REPLACE\n"
        )
        summary = apply_from_model_text(block, dry_run=True, root=self.root)
        self.assertFalse(summary.get("ok"))
        self.assertTrue(summary.get("repair_hints"))
        self.assertIn("[REPAIR]", summary.get("summary") or "")
        self.assertIn("SEARCH", (summary.get("summary") or ""))

    def test_create_file_with_empty_search(self) -> None:
        hunk = EditHunk(
            path="pkg/new_mod.py",
            search="",
            replace="VALUE = 42\n",
        )
        res = apply_edit(hunk, dry_run=False, root=self.root)
        self.assertTrue(res.ok, res.message)
        self.assertTrue((self.root / "pkg" / "new_mod.py").exists())
        v = verify("pkg/new_mod.py", root=self.root, must_contain=["42"], python_syntax=True)
        self.assertTrue(v.ok, v.message)

    def test_apply_edits_stop_on_error(self) -> None:
        plan = plan_edits(
            """\
pkg/sample.py
<<<<<<< SEARCH
NOPE
=======
x
>>>>>>> REPLACE
"""
        )
        results = apply_edits(plan, dry_run=True, root=self.root, stop_on_error=True)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)

    def test_verify_syntax_failure(self) -> None:
        bad = self.root / "pkg" / "bad.py"
        bad.write_text("def broken(\n", encoding="utf-8")
        v = verify("pkg/bad.py", root=self.root, python_syntax=True)
        self.assertFalse(v.ok)
        self.assertIn("syntax_error", v.message)


class TestCodeEditExecutorIntegration(unittest.TestCase):
    """Phase 2.7 — CODE path applies blocks when allow_tools; no tools → sandbox-only prompt path."""

    def setUp(self) -> None:
        self.root = Path(WORKSPACE) / ".isaac_code_edit_exec"
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        (self.root / "target.py").write_text("OLD = 1\n", encoding="utf-8")
        os.environ["ISAAC_CODE_EDIT"] = "1"
        os.environ["ISAAC_CODE_EDIT_DRY_RUN"] = "0"
        self.ex = object.__new__(Executor)
        self.ex.gate = MagicMock()
        self.ex.gate.require = MagicMock()
        self.ex.relay = MagicMock()
        self.block = (
            "target.py\n"
            "<<<<<<< SEARCH\n"
            "OLD = 1\n"
            "=======\n"
            "NEW = 2\n"
            ">>>>>>> REPLACE\n"
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)
        os.environ.pop("ISAAC_CODE_EDIT_DRY_RUN", None)

    def _task(self, *, allow_tools: bool) -> Task:
        return Task(
            id="t-code-edit",
            typ=TaskType.CODE,
            prompt="change OLD to NEW in target.py",
            beschreibung="edit",
            strategy=Strategy(allow_tools=allow_tools),
        )

    def test_code_with_allow_tools_applies_edit(self) -> None:
        task = self._task(allow_tools=True)
        self.ex.relay.ask_with_fallback = AsyncMock(return_value=(self.block, "test-provider"))

        async def _run() -> None:
            with patch("config.BASE_DIR", self.root):
                await Executor._execute_code(self.ex, task)

        asyncio.run(_run())
        self.assertEqual(task.status, TaskStatus.DONE, task.antwort)
        self.assertIn("CODE_EDIT", task.antwort)
        self.assertEqual((self.root / "target.py").read_text(encoding="utf-8"), "NEW = 2\n")
        events = [e.event for e in task.decision_trace.entries]
        self.assertIn("code_edit_start", events)
        self.assertIn("code_edit_done", events)
        self.assertTrue(any(t.get("name") == "code_edit" for t in task.used_tools))

    def test_code_without_allow_tools_does_not_apply_blocks(self) -> None:
        """allow_tools=False → no edit prompt path; blocks still might be in response but gated."""
        task = self._task(allow_tools=False)
        # Model returns edit blocks anyway; without allow_tools we must not apply
        self.ex.relay.ask_with_fallback = AsyncMock(return_value=(self.block, "test-provider"))

        async def _run() -> None:
            with patch("config.BASE_DIR", self.root):
                await Executor._execute_code(self.ex, task)

        asyncio.run(_run())
        # Should fall through to sandbox validation and fail (not valid isolated script)
        self.assertNotEqual((self.root / "target.py").read_text(encoding="utf-8"), "NEW = 2\n")
        self.assertTrue(
            task.status == TaskStatus.FAILED
            or "CODE_EDIT" not in (task.antwort or "")
        )
        self.assertNotIn("code_edit_done", [e.event for e in task.decision_trace.entries])

    def test_tool_runtime_helper_delegates(self) -> None:
        from tool_runtime import run_code_edit_from_model_text

        async def _run() -> dict:
            return await run_code_edit_from_model_text(
                self.block,
                dry_run=True,
                root=str(self.root),
            )

        summary = asyncio.run(_run())
        self.assertEqual(summary.get("mode"), "code_edit")
        self.assertTrue(summary.get("ok"), summary)
        self.assertTrue(summary.get("dry_run"))
        # dry_run must not write
        self.assertEqual((self.root / "target.py").read_text(encoding="utf-8"), "OLD = 1\n")


if __name__ == "__main__":
    unittest.main()
