"""Native coding strengths evals (Phase 4) — RepoMap, code_edit, git_ops, routing.

No live LLM. Temp dirs only. Fail-soft gates exercised where possible.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch


def _routing_cases() -> list[dict]:
    from isaac_core import IsaacKernel, Intent, detect_intent
    from low_complexity import classify_interaction_result

    kernel = object.__new__(IsaacKernel)
    cases: list[dict] = []

    def resolve(text: str) -> str:
        c = classify_interaction_result(text)
        return kernel._resolve_intent_from_classification(
            text, detect_intent(text), c.interaction_class
        )

    pairs = [
        ("code: fix greet()", Intent.CODE, True),
        (
            "Fix process_payment in pkg/checkout.py",
            Intent.CODE,
            True,
        ),
        (
            "implementiere eine Funktion foo in bar.py",
            Intent.CODE,
            True,
        ),
        ("Was ist 2+2?", Intent.CHAT, False),
        (
            "Erkläre mir das Wetter als sprachliches Motiv in Literatur",
            Intent.CHAT,
            False,
        ),
        ("Hallo Isaac", Intent.CHAT, False),
        ("Danke", Intent.CHAT, False),
    ]
    for text, expected, want_tools in pairs:
        intent = resolve(text)
        strat = kernel._select_response_strategy(
            user_input=text,
            intent=intent,
            interaction_class=classify_interaction_result(text).interaction_class,
            retrieval_ctx={},
        )
        cases.append(
            {
                "name": f"route:{text[:40]}",
                "ok": intent == expected
                and (strat.allow_tools is True if want_tools else strat.allow_tools is False or intent == Intent.CHAT),
                "detail": {
                    "intent": intent,
                    "expected": expected,
                    "allow_tools": strat.allow_tools,
                },
            }
        )
        if expected == Intent.CODE:
            cases[-1]["ok"] = intent == Intent.CODE and strat.allow_tools is True
        if expected == Intent.CHAT and text in ("Was ist 2+2?", "Erkläre mir das Wetter als sprachliches Motiv in Literatur"):
            cases[-1]["ok"] = intent == Intent.CHAT and strat.allow_tools is False
    return cases


def _repomap_cases(tmp: Path) -> list[dict]:
    os.environ["ISAAC_REPO_MAP"] = "1"
    (tmp / "pkg").mkdir()
    (tmp / "pkg" / "checkout.py").write_text(
        "def process_payment(x):\n    return True\n\ndef other():\n    pass\n",
        encoding="utf-8",
    )
    (tmp / "pkg" / "ads.py").write_text("def banner():\n    return 1\n", encoding="utf-8")
    from repo_map import get_ranked_context, maybe_enrich_retrieval_with_repo_map

    ranked = get_ranked_context(
        "fix process_payment bug",
        max_tokens=400,
        root=tmp,
    )
    ctx = maybe_enrich_retrieval_with_repo_map(
        {"query": "x"},
        user_input="fix process_payment",
        intent="code",
        root=tmp,
    )
    chat = maybe_enrich_retrieval_with_repo_map(
        {"query": "x"},
        user_input="fix process_payment",
        intent="chat",
        root=tmp,
    )
    return [
        {
            "name": "repomap_ranks_payment",
            "ok": ranked.enabled
            and "process_payment" in ranked.text
            and "checkout.py" in "".join(ranked.files),
            "detail": {"files": list(ranked.files), "backend": ranked.backend},
        },
        {
            "name": "repomap_enrich_code_only",
            "ok": "code_map" in ctx and "code_map" not in chat,
            "detail": {"code_keys": list(ctx.keys()), "chat_keys": list(chat.keys())},
        },
    ]


def _code_edit_git_e2e(tmp: Path) -> list[dict]:
    """Mini E2E: parse SEARCH/REPLACE → apply → commit (no LLM)."""
    os.environ["ISAAC_CODE_EDIT"] = "1"
    os.environ["ISAAC_CODE_EDIT_DRY_RUN"] = "0"
    os.environ["ISAAC_GIT_OPS"] = "1"
    os.environ["ISAAC_GIT_OPS_DRY_RUN"] = "0"
    os.environ["ISAAC_GIT_OPS_AUTO_COMMIT"] = "0"

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Eval",
        "GIT_AUTHOR_EMAIL": "eval@example.com",
        "GIT_COMMITTER_NAME": "Eval",
        "GIT_COMMITTER_EMAIL": "eval@example.com",
    }
    subprocess.run(["git", "init"], cwd=str(tmp), check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "config", "user.email", "eval@example.com"],
        cwd=str(tmp),
        check=True,
        capture_output=True,
        env=env,
    )
    subprocess.run(
        ["git", "config", "user.name", "Eval"],
        cwd=str(tmp),
        check=True,
        capture_output=True,
        env=env,
    )
    target = tmp / "mod.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "mod.py"], cwd=str(tmp), check=True, capture_output=True, env=env
    )
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=str(tmp),
        check=True,
        capture_output=True,
        env=env,
    )

    block = (
        "mod.py\n"
        "<<<<<<< SEARCH\n"
        "VALUE = 1\n"
        "=======\n"
        "VALUE = 2\n"
        ">>>>>>> REPLACE\n"
    )
    from code_edit import apply_from_model_text, plan_edits
    from git_ops import git_commit, git_status

    plan = plan_edits(block)
    summary = apply_from_model_text(block, dry_run=False, root=tmp)
    content_ok = target.read_text(encoding="utf-8") == "VALUE = 2\n"
    st = git_status(tmp)
    commit = git_commit(
        "Eval: bump VALUE",
        paths=["mod.py"],
        root=tmp,
        dry_run=False,
    )
    # Ambiguous match refuse
    amb = tmp / "dup.py"
    amb.write_text("a=1\na=1\n", encoding="utf-8")
    from code_edit import EditHunk, apply_edit

    amb_res = apply_edit(
        EditHunk(path="dup.py", search="a=1\n", replace="a=2\n"),
        dry_run=True,
        root=tmp,
    )

    return [
        {
            "name": "e2e_plan_has_hunk",
            "ok": plan.ok and len(plan.hunks) == 1,
            "detail": plan.as_dict(),
        },
        {
            "name": "e2e_apply_writes",
            "ok": bool(summary.get("ok")) and content_ok,
            "detail": {"summary_ok": summary.get("ok"), "content": target.read_text(encoding="utf-8")},
        },
        {
            "name": "e2e_git_commit",
            "ok": commit.ok and bool((commit.meta or {}).get("sha")),
            "detail": commit.as_dict(),
        },
        {
            "name": "e2e_status_clean_after_commit",
            "ok": st.ok and commit.ok,
            "detail": {"dirty_before_commit": st.meta.get("dirty")},
        },
        {
            "name": "e2e_ambiguous_search_refused",
            "ok": (not amb_res.ok) and "ambiguous" in amb_res.message,
            "detail": amb_res.message,
        },
    ]


def _donot_invariants() -> list[dict]:
    """Lightweight Do-NOT checks: modules exist, no aider import dependency."""
    import importlib.util

    names = ["repo_map", "code_edit", "git_ops"]
    present = all(importlib.util.find_spec(n) is not None for n in names)
    # source must not import aider package
    root = Path(__file__).resolve().parents[1]
    bad = []
    for n in names:
        src = (root / f"{n}.py").read_text(encoding="utf-8", errors="replace")
        if re_search_aider(src):
            bad.append(n)
    return [
        {
            "name": "native_modules_present",
            "ok": present,
            "detail": names,
        },
        {
            "name": "no_aider_package_import",
            "ok": not bad,
            "detail": {"offenders": bad},
        },
    ]


def re_search_aider(src: str) -> bool:
    import re

    return bool(re.search(r"^\s*(import|from)\s+aider\b", src, re.M))


def run() -> dict:
    prev = {
        k: os.environ.get(k)
        for k in (
            "ISAAC_REPO_MAP",
            "ISAAC_CODE_EDIT",
            "ISAAC_CODE_EDIT_DRY_RUN",
            "ISAAC_GIT_OPS",
            "ISAAC_GIT_OPS_DRY_RUN",
            "ISAAC_GIT_OPS_AUTO_COMMIT",
        )
    }
    tmp = Path(tempfile.mkdtemp(prefix="isaac_coding_eval_"))
    cases: list[dict] = []
    try:
        cases.extend(_routing_cases())
        map_root = tmp / "maproot"
        map_root.mkdir(parents=True, exist_ok=True)
        cases.extend(_repomap_cases(map_root))
        e2e_root = tmp / "e2e"
        e2e_root.mkdir(parents=True, exist_ok=True)
        cases.extend(_code_edit_git_e2e(e2e_root))
        cases.extend(_donot_invariants())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "suite": "coding",
        "passed": passed,
        "total": len(cases),
        "cases": cases,
    }
