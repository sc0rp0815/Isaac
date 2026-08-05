"""Native structured code edits for Isaac (Aider-inspired SEARCH/REPLACE).

GRÜN-layer apply path — does **not** reclassify or choose strategy.
Every write goes through path resolution (file_access) + Constitution gate.

Phase 2.1 decisions
-------------------
Format
    Aider-style blocks::

        path/to/file.py
        <<<<<<< SEARCH
        old lines
        =======
        new lines
        >>>>>>> REPLACE

API
    plan_edits(text) -> EditPlan
    apply_edit(hunk, *, dry_run=True) -> ApplyResult
    apply_edits(plan, *, dry_run=True) -> list[ApplyResult]
    verify(path, ...) -> VerifyResult

Safety (stricter than Aider fuzzy apply)
    - Exact unique SEARCH match only (no fuzzy / edit-distance replace)
    - Multiple matches → refuse
    - Path must resolve under allowed roots (file_access.resolve_path)
    - Writes require Constitution allow (same family as file write)
    - dry_run default True for apply_edit helpers used by agents

Not in 2.1
    tool_runtime wiring, executor CODE-path rewrite, git commit (Phase 3),
    wholesale aider import, multi-file auto-discovery across chat files.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

# ── Block markers (Aider-compatible) ─────────────────────────────────────────

_HEAD = re.compile(r"^<{5,9}\s*SEARCH\s*$")
_DIVIDER = re.compile(r"^={5,9}\s*$")
_UPDATED = re.compile(r"^>{5,9}\s*REPLACE\s*$")
_FENCE_LINE = re.compile(r"^```")


@dataclass(frozen=True)
class EditHunk:
    path: str
    search: str
    replace: str
    source_line: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "search": self.search,
            "replace": self.replace,
            "source_line": self.source_line,
            "is_create": not (self.search or "").strip(),
        }


@dataclass
class EditPlan:
    hunks: list[EditHunk] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_block_count: int = 0

    @property
    def ok(self) -> bool:
        return bool(self.hunks) and not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "hunks": [h.as_dict() for h in self.hunks],
            "errors": list(self.errors),
            "raw_block_count": self.raw_block_count,
        }


@dataclass(frozen=True)
class ApplyResult:
    ok: bool
    path: str
    message: str
    dry_run: bool = True
    written: bool = False
    diff_preview: str = ""
    blocked_by: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "message": self.message,
            "dry_run": self.dry_run,
            "written": self.written,
            "diff_preview": self.diff_preview,
            "blocked_by": list(self.blocked_by),
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    path: str
    message: str
    checks: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "message": self.message,
            "checks": dict(self.checks),
        }


def _strip_filename(line: str) -> str:
    name = (line or "").strip()
    if not name or name == "...":
        return ""
    # fences / bullets
    name = name.lstrip("#").strip()
    name = name.strip("`").strip("*").strip()
    if name.startswith("```"):
        name = name[3:].strip()
    if name.endswith(":"):
        name = name[:-1].strip()
    # language fence alone
    if name in {"python", "py", "javascript", "js", "ts", "tsx", "go", "rust", "java"}:
        return ""
    return name


def _looks_like_path(name: str) -> bool:
    if not name or " " in name.strip() and "/" not in name and "\\" not in name:
        # allow simple "file.py"
        if re.match(r"^[\w./\\-]+\.\w{1,8}$", name.strip()):
            return True
        return False
    return bool(re.search(r"[./\\]", name) or re.search(r"\.\w{1,8}$", name))


def plan_edits(text: str) -> EditPlan:
    """Parse SEARCH/REPLACE blocks from model (or user) text into an EditPlan."""
    plan = EditPlan()
    if not (text or "").strip():
        plan.errors.append("empty_input")
        return plan

    lines = text.splitlines(keepends=True)
    i = 0
    current_filename = ""
    n_blocks = 0

    while i < len(lines):
        line = lines[i]
        if not _HEAD.match(line.strip()):
            # track possible filename lines before a block
            cand = _strip_filename(line.rstrip("\n"))
            if cand and _looks_like_path(cand) and not _FENCE_LINE.match(line.strip()):
                current_filename = cand
            i += 1
            continue

        n_blocks += 1
        # filename: look back up to 3 non-empty lines
        filename = current_filename
        for back in range(1, 4):
            if i - back < 0:
                break
            prev = lines[i - back].rstrip("\n")
            if _FENCE_LINE.match(prev.strip()):
                # try line before fence
                continue
            cand = _strip_filename(prev)
            if cand and _looks_like_path(cand):
                filename = cand
                break

        if not filename:
            plan.errors.append(f"line {i + 1}: missing_filename before SEARCH")
            i += 1
            continue

        original: list[str] = []
        i += 1
        while i < len(lines) and not _DIVIDER.match(lines[i].strip()):
            if _UPDATED.match(lines[i].strip()) or _HEAD.match(lines[i].strip()):
                break
            original.append(lines[i])
            i += 1

        if i >= len(lines) or not _DIVIDER.match(lines[i].strip()):
            plan.errors.append(f"path={filename}: missing_divider")
            continue

        updated: list[str] = []
        i += 1
        while i < len(lines) and not _UPDATED.match(lines[i].strip()):
            if _HEAD.match(lines[i].strip()) or _DIVIDER.match(lines[i].strip()):
                break
            updated.append(lines[i])
            i += 1

        if i >= len(lines) or not _UPDATED.match(lines[i].strip()):
            plan.errors.append(f"path={filename}: missing_replace_marker")
            continue

        i += 1  # skip REPLACE line
        search = "".join(original)
        replace = "".join(updated)
        # Drop trailing fence-only noise inside replace if model closed early
        plan.hunks.append(
            EditHunk(
                path=filename.replace("\\", "/"),
                search=search,
                replace=replace,
                source_line=i,
            )
        )
        current_filename = filename

    plan.raw_block_count = n_blocks
    if n_blocks == 0 and not plan.errors:
        plan.errors.append("no_search_replace_blocks")
    return plan


def _preview_diff(before: str, after: str, path: str, max_lines: int = 40) -> str:
    import difflib

    a = before.splitlines(keepends=True)
    b = after.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(a, b, fromfile=f"a/{path}", tofile=f"b/{path}", n=2)
    )
    if len(diff) > max_lines:
        diff = diff[:max_lines] + [f"... ({len(diff) - max_lines} more diff lines)\n"]
    return "".join(diff)


def _apply_unique_replace(content: str, search: str, replace: str) -> tuple[str | None, str]:
    """Exact unique match. Empty search → create/append semantics."""
    if not (search or "").strip():
        # create new content or append
        if content:
            return content + replace, "append"
        return replace, "create"

    count = content.count(search)
    if count == 0:
        # try newline-normalized exact
        norm_c = content.replace("\r\n", "\n")
        norm_s = search.replace("\r\n", "\n")
        count = norm_c.count(norm_s)
        if count == 1:
            return norm_c.replace(norm_s, replace.replace("\r\n", "\n"), 1), "exact_normalized"
        if count == 0:
            return None, "search_not_found"
        return None, f"search_ambiguous:{count}"

    if count > 1:
        return None, f"search_ambiguous:{count}"

    return content.replace(search, replace, 1), "exact"


def _constitution_gate_write(path: str, *, is_delete: bool = False) -> tuple[bool, list[str], list[str]]:
    """Return (allowed, blocked_by, warnings)."""
    try:
        from config import Level, is_owner_equivalent_mode
        from constitution_override import apply_constitution_gate, build_override_context
    except Exception as exc:
        return False, [f"gate_import_error:{type(exc).__name__}"], []

    action = "file_delete" if is_delete else "system_command"
    gate = apply_constitution_gate(
        action,
        {
            "outside_effect": True,
            "audit_logged": True,
            "risk": "high",
            "code_edit": True,
            "path": path[:200],
        },
        build_override_context(
            source="code_edit",
            caller_level=Level.STEFFEN if is_owner_equivalent_mode() else Level.TASK,
            owner_confirmed=is_owner_equivalent_mode(),
            override_reason="owner_equivalent_mode" if is_owner_equivalent_mode() else "",
        ),
    )
    return (
        bool(gate.get("allowed")),
        list(gate.get("blocked_by") or []),
        list(gate.get("warnings") or []),
    )


def apply_edit(
    hunk: EditHunk,
    *,
    dry_run: bool = True,
    root: Path | str | None = None,
    decision_trace: Any | None = None,
    skip_constitution: bool = False,
) -> ApplyResult:
    """Apply one hunk. Default dry_run=True — no disk write unless False."""
    from file_access import resolve_path

    path_raw = (hunk.path or "").strip()
    if not path_raw:
        return ApplyResult(ok=False, path="", message="empty_path", dry_run=dry_run)

    # Optional root prefix for relative paths in tests
    if root and not Path(path_raw).is_absolute():
        candidate = str((Path(root) / path_raw).resolve())
    else:
        candidate = path_raw

    resolved, err = resolve_path(candidate)
    if not resolved:
        # try relative to repo BASE_DIR via config if path was repo-relative
        if root:
            resolved, err = resolve_path(str(Path(root) / path_raw))
        if not resolved:
            return ApplyResult(
                ok=False,
                path=path_raw,
                message=f"path_blocked:{err}",
                dry_run=dry_run,
                blocked_by=("path_resolve",),
            )

    rel_display = path_raw.replace("\\", "/")
    if not skip_constitution:
        allowed, blocked, warnings = _constitution_gate_write(str(resolved))
        if not allowed:
            result = ApplyResult(
                ok=False,
                path=rel_display,
                message=f"constitution_blocked:{','.join(blocked)}",
                dry_run=dry_run,
                blocked_by=tuple(blocked),
                meta={"warnings": warnings},
            )
            _trace_apply(decision_trace, result)
            return result

    exists = resolved.exists()
    if exists and resolved.is_dir():
        return ApplyResult(
            ok=False,
            path=rel_display,
            message="path_is_directory",
            dry_run=dry_run,
        )

    try:
        before = resolved.read_text(encoding="utf-8") if exists else ""
    except OSError as exc:
        return ApplyResult(
            ok=False,
            path=rel_display,
            message=f"read_error:{type(exc).__name__}",
            dry_run=dry_run,
        )

    is_create = not (hunk.search or "").strip() and not exists
    if not exists and (hunk.search or "").strip():
        return ApplyResult(
            ok=False,
            path=rel_display,
            message="file_missing_for_search",
            dry_run=dry_run,
        )

    after, mode = _apply_unique_replace(before, hunk.search, hunk.replace)
    if after is None:
        return ApplyResult(
            ok=False,
            path=rel_display,
            message=mode,
            dry_run=dry_run,
            meta={"mode": mode},
        )

    if after == before:
        return ApplyResult(
            ok=False,
            path=rel_display,
            message="no_change",
            dry_run=dry_run,
            meta={"mode": mode},
        )

    preview = _preview_diff(before, after, rel_display)
    if dry_run:
        result = ApplyResult(
            ok=True,
            path=rel_display,
            message="dry_run_ok",
            dry_run=True,
            written=False,
            diff_preview=preview,
            meta={"mode": mode, "is_create": is_create, "abs": str(resolved)},
        )
        _trace_apply(decision_trace, result)
        return result

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(after, encoding="utf-8")
    except OSError as exc:
        result = ApplyResult(
            ok=False,
            path=rel_display,
            message=f"write_error:{type(exc).__name__}",
            dry_run=False,
            meta={"mode": mode},
        )
        _trace_apply(decision_trace, result)
        return result

    try:
        from audit import AuditLog

        AuditLog.action(
            "CodeEdit",
            "apply",
            f"{rel_display} mode={mode}",
            erfolg=True,
        )
    except Exception:
        pass

    result = ApplyResult(
        ok=True,
        path=rel_display,
        message="applied",
        dry_run=False,
        written=True,
        diff_preview=preview,
        meta={"mode": mode, "is_create": is_create, "abs": str(resolved)},
    )
    _trace_apply(decision_trace, result)
    return result


def apply_edits(
    plan: EditPlan,
    *,
    dry_run: bool = True,
    root: Path | str | None = None,
    decision_trace: Any | None = None,
    stop_on_error: bool = True,
    skip_constitution: bool = False,
) -> list[ApplyResult]:
    """Apply all hunks in order. Fails fast by default."""
    results: list[ApplyResult] = []
    if plan.errors and not plan.hunks:
        results.append(
            ApplyResult(
                ok=False,
                path="",
                message="plan_invalid:" + ";".join(plan.errors[:5]),
                dry_run=dry_run,
            )
        )
        return results

    for hunk in plan.hunks:
        res = apply_edit(
            hunk,
            dry_run=dry_run,
            root=root,
            decision_trace=decision_trace,
            skip_constitution=skip_constitution,
        )
        results.append(res)
        if not res.ok and stop_on_error:
            break
    return results


def verify(
    path: str,
    *,
    root: Path | str | None = None,
    must_contain: Sequence[str] | None = None,
    must_not_contain: Sequence[str] | None = None,
    python_syntax: bool | None = None,
) -> VerifyResult:
    """Post-edit checks: existence, substrings, optional Python parse."""
    from file_access import resolve_path

    candidate = path
    if root and not Path(path).is_absolute():
        candidate = str((Path(root) / path).resolve())

    resolved, err = resolve_path(candidate)
    if not resolved:
        if root:
            resolved, err = resolve_path(str(Path(root) / path))
        if not resolved:
            return VerifyResult(ok=False, path=path, message=f"path_blocked:{err}")

    if not resolved.exists():
        return VerifyResult(ok=False, path=path, message="missing_file")

    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return VerifyResult(ok=False, path=path, message=f"read_error:{type(exc).__name__}")

    checks: dict[str, Any] = {"bytes": len(text.encode("utf-8")), "lines": text.count("\n") + 1}

    for s in must_contain or ():
        ok = s in text
        checks[f"contains:{s[:40]}"] = ok
        if not ok:
            return VerifyResult(
                ok=False,
                path=path,
                message=f"missing_substring:{s[:80]}",
                checks=checks,
            )

    for s in must_not_contain or ():
        ok = s not in text
        checks[f"not_contains:{s[:40]}"] = ok
        if not ok:
            return VerifyResult(
                ok=False,
                path=path,
                message=f"forbidden_substring:{s[:80]}",
                checks=checks,
            )

    use_py = python_syntax if python_syntax is not None else path.endswith(".py")
    if use_py:
        try:
            ast.parse(text)
            checks["python_syntax"] = True
        except SyntaxError as exc:
            checks["python_syntax"] = False
            return VerifyResult(
                ok=False,
                path=path,
                message=f"syntax_error:{exc.msg}",
                checks=checks,
            )

    return VerifyResult(ok=True, path=path, message="verified", checks=checks)


def _trace_apply(decision_trace: Any, result: ApplyResult) -> None:
    if decision_trace is None:
        return
    try:
        from decision_trace import TracePhase

        decision_trace.add(
            TracePhase.EXECUTION,
            "code_edit_apply",
            {
                "ok": result.ok,
                "path": result.path[:200],
                "dry_run": result.dry_run,
                "written": result.written,
                "message": result.message[:120],
                "blocked_by": list(result.blocked_by)[:8],
                "mode": (result.meta or {}).get("mode"),
            },
        )
    except Exception:
        pass


def code_edit_enabled() -> bool:
    raw = (os.environ.get("ISAAC_CODE_EDIT") or "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def code_edit_dry_run() -> bool:
    """When true, plan/apply never write (ISAAC_CODE_EDIT_DRY_RUN=1)."""
    raw = (os.environ.get("ISAAC_CODE_EDIT_DRY_RUN") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return False


def looks_like_edit_blocks(text: str) -> bool:
    """Cheap pre-check before full plan_edits."""
    if not text:
        return False
    return bool(re.search(r"^<{5,9}\s*SEARCH\s*$", text, re.M)) and bool(
        re.search(r"^>{5,9}\s*REPLACE\s*$", text, re.M)
    )


def apply_from_model_text(
    text: str,
    *,
    dry_run: bool | None = None,
    root: Path | str | None = None,
    decision_trace: Any | None = None,
    stop_on_error: bool = True,
    skip_constitution: bool = False,
) -> dict[str, Any]:
    """Parse model text and apply SEARCH/REPLACE hunks.

    Returns a serializable summary for task.antwort / traces.
    """
    if dry_run is None:
        dry_run = code_edit_dry_run()

    plan = plan_edits(text or "")
    if not plan.hunks:
        return {
            "ok": False,
            "mode": "code_edit",
            "reason": "no_hunks",
            "plan": plan.as_dict(),
            "results": [],
            "dry_run": dry_run,
        }

    results = apply_edits(
        plan,
        dry_run=dry_run,
        root=root,
        decision_trace=decision_trace,
        stop_on_error=stop_on_error,
        skip_constitution=skip_constitution,
    )
    all_ok = bool(results) and all(r.ok for r in results)
    verifies: list[dict[str, Any]] = []
    if all_ok and not dry_run:
        seen: set[str] = set()
        for r in results:
            if not r.ok or r.path in seen:
                continue
            seen.add(r.path)
            # Light verify: file exists + python syntax when .py
            v = verify(r.path, root=root, python_syntax=None)
            verifies.append(v.as_dict())
            if not v.ok:
                all_ok = False

    summary_lines = []
    for r in results:
        flag = "ok" if r.ok else "FAIL"
        wr = "written" if r.written else ("dry_run" if r.dry_run else "no_write")
        summary_lines.append(f"- [{flag}] {r.path}: {r.message} ({wr})")
        if r.diff_preview and len(summary_lines) < 12:
            # keep short
            preview = r.diff_preview.strip().splitlines()[:8]
            summary_lines.extend(f"    {ln}" for ln in preview)

    return {
        "ok": all_ok,
        "mode": "code_edit",
        "reason": "applied" if all_ok else "partial_or_failed",
        "plan": plan.as_dict(),
        "results": [r.as_dict() for r in results],
        "verifies": verifies,
        "dry_run": dry_run,
        "summary": "\n".join(summary_lines),
        "n_hunks": len(plan.hunks),
        "n_ok": sum(1 for r in results if r.ok),
    }
