"""Phase 3.1 — lightweight git_ops unit tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("ISAAC_DISABLE_VECTOR_MEMORY", "1")
os.environ["ISAAC_GIT_OPS"] = "1"
os.environ["ISAAC_GIT_OPS_DRY_RUN"] = "0"

from decision_trace import DecisionTrace, TracePhase
from git_ops import (
    find_repo_root,
    format_git_result,
    git_commit,
    git_diff,
    git_ops_enabled,
    git_restore,
    git_status,
)


def _run(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Isaac Test",
            "GIT_AUTHOR_EMAIL": "isaac-test@example.com",
            "GIT_COMMITTER_NAME": "Isaac Test",
            "GIT_COMMITTER_EMAIL": "isaac-test@example.com",
        },
    )


class TestGitOpsPhase31(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmpdir.name)
        _run(self.repo, "init")
        _run(self.repo, "config", "user.email", "isaac-test@example.com")
        _run(self.repo, "config", "user.name", "Isaac Test")
        (self.repo / "readme.txt").write_text("v1\n", encoding="utf-8")
        _run(self.repo, "add", "readme.txt")
        _run(self.repo, "commit", "-m", "initial")
        os.environ["ISAAC_GIT_OPS"] = "1"
        os.environ["ISAAC_GIT_OPS_DRY_RUN"] = "0"

    def tearDown(self) -> None:
        # .git object packs can race with rmdir on some filesystems
        try:
            shutil.rmtree(self.repo, ignore_errors=True)
        except Exception:
            pass
        try:
            self._tmpdir.cleanup()
        except OSError:
            pass

    def test_find_repo_root(self) -> None:
        nested = self.repo / "sub" / "dir"
        nested.mkdir(parents=True)
        self.assertEqual(find_repo_root(nested), self.repo.resolve())

    def test_status_and_diff_dirty(self) -> None:
        (self.repo / "readme.txt").write_text("v2\n", encoding="utf-8")
        st = git_status(self.repo)
        self.assertTrue(st.ok, st.message)
        self.assertTrue(st.meta.get("dirty"))
        d = git_diff(self.repo, paths=["readme.txt"])
        self.assertTrue(d.ok, d.message)
        self.assertIn("v2", d.stdout)
        self.assertIn("-v1", d.stdout.replace(" ", "") or d.stdout)

    def test_commit_with_message_and_paths(self) -> None:
        (self.repo / "readme.txt").write_text("v2\n", encoding="utf-8")
        (self.repo / "extra.txt").write_text("x\n", encoding="utf-8")
        trace = DecisionTrace()
        res = git_commit(
            "Update readme to v2",
            paths=["readme.txt"],
            root=self.repo,
            dry_run=False,
            decision_trace=trace,
        )
        self.assertTrue(res.ok, res.message)
        self.assertTrue(res.meta.get("sha"))
        # extra.txt must remain untracked/uncommitted
        st = git_status(self.repo)
        self.assertIn("extra.txt", st.stdout)
        events = [e.event for e in trace.entries if e.phase == TracePhase.EXECUTION]
        self.assertIn("git_ops_commit", events)

    def test_commit_dry_run_no_sha_change(self) -> None:
        before = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(self.repo), text=True
        ).strip()
        (self.repo / "readme.txt").write_text("v3\n", encoding="utf-8")
        res = git_commit(
            "should not land",
            paths=["readme.txt"],
            root=self.repo,
            dry_run=True,
        )
        self.assertTrue(res.ok, res.message)
        self.assertTrue(res.dry_run)
        after = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(self.repo), text=True
        ).strip()
        self.assertEqual(before, after)

    def test_commit_refuses_empty_message(self) -> None:
        (self.repo / "readme.txt").write_text("v9\n", encoding="utf-8")
        res = git_commit("  \n  ", paths=["readme.txt"], root=self.repo)
        self.assertFalse(res.ok)
        self.assertEqual(res.message, "empty_commit_message")

    def test_commit_refuses_no_paths(self) -> None:
        res = git_commit("msg", paths=[], root=self.repo, allow_all_tracked=False)
        self.assertFalse(res.ok)
        self.assertIn("no_paths", res.message)

    def test_path_escape_blocked(self) -> None:
        res = git_diff(self.repo, paths=["../outside.txt"])
        self.assertFalse(res.ok)
        self.assertTrue(
            "path_outside_repo" in res.message or "path_escape" in res.message
        )

    def test_restore_discards_worktree(self) -> None:
        (self.repo / "readme.txt").write_text("dirty\n", encoding="utf-8")
        res = git_restore(["readme.txt"], root=self.repo, dry_run=False)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(
            (self.repo / "readme.txt").read_text(encoding="utf-8"), "v1\n"
        )

    def test_disabled(self) -> None:
        os.environ["ISAAC_GIT_OPS"] = "0"
        self.assertFalse(git_ops_enabled())
        res = git_status(self.repo)
        self.assertFalse(res.ok)
        self.assertIn("disabled", res.message)

    def test_format_git_result(self) -> None:
        st = git_status(self.repo)
        text = format_git_result(st)
        self.assertIn("[GIT:status]", text)

    def test_parse_owner_git_status_and_commit(self) -> None:
        from git_ops import parse_owner_git_command, run_parsed_git_op

        p = parse_owner_git_command("git status")
        self.assertEqual(p.get("op"), "status")
        r = run_parsed_git_op(p, root=self.repo)
        self.assertTrue(r.ok, r.message)

        (self.repo / "readme.txt").write_text("v-owner\n", encoding="utf-8")
        p2 = parse_owner_git_command('git commit -m "owner msg" readme.txt')
        self.assertEqual(p2.get("op"), "commit")
        self.assertEqual(p2.get("message"), "owner msg")
        self.assertEqual(p2.get("paths"), ["readme.txt"])
        r2 = run_parsed_git_op(p2, root=self.repo, dry_run=False)
        self.assertTrue(r2.ok, r2.message)
        self.assertTrue(r2.meta.get("sha"))

    def test_parse_push_falls_through(self) -> None:
        from git_ops import parse_owner_git_command

        self.assertIsNone(parse_owner_git_command("git push origin main"))


class TestGitOpsPhase37Integration(unittest.TestCase):
    """Phase 3.7 — auto-commit after code_edit + tool_runtime helper."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmpdir.name)
        _run(self.repo, "init")
        _run(self.repo, "config", "user.email", "isaac-test@example.com")
        _run(self.repo, "config", "user.name", "Isaac Test")
        (self.repo / "app.py").write_text("X = 1\n", encoding="utf-8")
        _run(self.repo, "add", "app.py")
        _run(self.repo, "commit", "-m", "base")
        os.environ["ISAAC_GIT_OPS"] = "1"
        os.environ["ISAAC_GIT_OPS_AUTO_COMMIT"] = "1"
        os.environ["ISAAC_GIT_OPS_DRY_RUN"] = "0"
        os.environ["ISAAC_CODE_EDIT"] = "1"
        os.environ["ISAAC_CODE_EDIT_DRY_RUN"] = "0"

    def tearDown(self) -> None:
        os.environ.pop("ISAAC_GIT_OPS_AUTO_COMMIT", None)
        try:
            shutil.rmtree(self.repo, ignore_errors=True)
        except Exception:
            pass
        try:
            self._tmpdir.cleanup()
        except OSError:
            pass

    def test_auto_commit_after_code_edit(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from executor import Executor, Strategy, Task, TaskStatus, TaskType

        block = (
            "app.py\n"
            "<<<<<<< SEARCH\n"
            "X = 1\n"
            "=======\n"
            "X = 2\n"
            ">>>>>>> REPLACE\n"
        )
        ex = object.__new__(Executor)
        ex.gate = MagicMock()
        ex.gate.require = MagicMock()
        ex.relay = MagicMock()
        ex.relay.ask_with_fallback = AsyncMock(return_value=(block, "test"))
        task = Task(
            id="t-git-auto",
            typ=TaskType.CODE,
            prompt="bump X",
            beschreibung="bump X to 2",
            strategy=Strategy(allow_tools=True),
        )

        async def _run() -> None:
            with patch("config.BASE_DIR", self.repo):
                await Executor._execute_code(ex, task)

        asyncio.run(_run())
        self.assertEqual(task.status, TaskStatus.DONE, task.antwort)
        self.assertIn("CODE_EDIT", task.antwort)
        self.assertIn("[GIT:commit]", task.antwort)
        self.assertEqual((self.repo / "app.py").read_text(encoding="utf-8"), "X = 2\n")
        events = [e.event for e in task.decision_trace.entries]
        self.assertIn("git_ops_auto_commit_done", events)
        log = subprocess.check_output(
            ["git", "log", "-1", "--pretty=%s"], cwd=str(self.repo), text=True
        ).strip()
        self.assertTrue(log.startswith("Isaac"), log)

    def test_tool_runtime_run_git_ops_status(self) -> None:
        import asyncio
        from tool_runtime import run_git_ops

        async def _run() -> dict:
            return await run_git_ops("git status", root=str(self.repo))

        d = asyncio.run(_run())
        self.assertTrue(d.get("ok"), d)
        self.assertIn("formatted", d)


if __name__ == "__main__":
    unittest.main()
