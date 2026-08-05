"""Lightweight Git ops for Isaac (Aider-inspired commit hygiene — not a full git UI).

GRÜN-layer: subprocess-only, allowlisted commands. No force-push, no history rewrite
by default. Commit messages may come from the LLM; **Isaac** always runs git.

Phase 3.1 API
-------------
    git_status(root=...) -> GitResult
    git_diff(root=..., paths=..., staged=...) -> GitResult
    git_commit(message, paths=..., root=..., dry_run=...) -> GitResult
    git_restore(paths, root=..., dry_run=...) -> GitResult   # uncommitted only

Safety
------
- Only ``git`` via allowlisted subcommands
- No push / force / rebase / reset --hard / clean -fd
- Paths resolved under repo root; optional file_access root checks for paths
- Constitution gate on commit + restore (outside_effect, high risk)
- Env: ISAAC_GIT_OPS=0 disables; ISAAC_GIT_OPS_DRY_RUN=1 forces dry-run

Not in 3.1
----------
Executor/tool_runtime wiring (3.7), remote push, multi-remote, GPG signing UI.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

_ALLOWED_SUBCOMMANDS = frozenset(
    {
        "status",
        "diff",
        "add",
        "commit",
        "restore",
        "rev-parse",
        "log",
        "show",
    }
)

# Hard block even if someone extends later
_BLOCKED_ARGS = re.compile(
    r"(--force|-f\b|push|rebase|reset\s+--hard|clean\s+-|filter-branch|update-ref)",
    re.I,
)


@dataclass(frozen=True)
class GitResult:
    ok: bool
    action: str
    message: str
    stdout: str = ""
    stderr: str = ""
    dry_run: bool = False
    root: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "message": self.message,
            "stdout": self.stdout[:8000],
            "stderr": self.stderr[:2000],
            "dry_run": self.dry_run,
            "root": self.root,
            "meta": dict(self.meta),
        }


def git_ops_enabled() -> bool:
    raw = (os.environ.get("ISAAC_GIT_OPS") or "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def git_ops_dry_run() -> bool:
    raw = (os.environ.get("ISAAC_GIT_OPS_DRY_RUN") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return False


def _git_bin() -> str | None:
    return shutil.which("git")


def find_repo_root(start: Path | str | None = None) -> Path | None:
    """Walk up for .git; fail-soft."""
    if start is None:
        try:
            from config import BASE_DIR

            cur = Path(BASE_DIR).resolve()
        except Exception:
            cur = Path.cwd().resolve()
    else:
        cur = Path(start).expanduser().resolve()
    if not cur.exists():
        return None
    if cur.is_file():
        cur = cur.parent
    for p in [cur, *cur.parents]:
        if (p / ".git").exists():
            return p
    return None


def _run_git(
    root: Path,
    args: Sequence[str],
    *,
    check_blocklist: bool = True,
    timeout: float = 30.0,
) -> tuple[int, str, str]:
    if not args:
        return 1, "", "empty_args"
    sub = str(args[0]).lstrip("-")
    # first token must be allowlisted subcommand
    if sub not in _ALLOWED_SUBCOMMANDS:
        return 1, "", f"subcommand_not_allowed:{sub}"
    full = ["git", "-C", str(root), *args]
    joined = " ".join(full)
    if check_blocklist and _BLOCKED_ARGS.search(joined):
        return 1, "", "blocked_git_args"
    try:
        proc = subprocess.run(
            full,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                **os.environ,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0",
            },
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"
    except FileNotFoundError:
        return 1, "", "git_not_found"
    except Exception as exc:
        return 1, "", f"error:{type(exc).__name__}"


def _constitution_gate(action_label: str) -> tuple[bool, list[str], list[str]]:
    try:
        from config import Level, is_owner_equivalent_mode
        from constitution_override import apply_constitution_gate, build_override_context
    except Exception as exc:
        return False, [f"gate_import_error:{type(exc).__name__}"], []

    gate = apply_constitution_gate(
        "system_command",
        {
            "outside_effect": True,
            "audit_logged": True,
            "risk": "high",
            "git_ops": True,
            "git_action": action_label[:80],
        },
        build_override_context(
            source="git_ops",
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


def _normalize_paths(root: Path, paths: Sequence[str] | None) -> tuple[list[str], str | None]:
    """Return paths relative to root; reject escapes."""
    if not paths:
        return [], None
    out: list[str] = []
    root_r = root.resolve()
    for raw in paths:
        if not (raw or "").strip():
            continue
        p = Path(raw)
        if not p.is_absolute():
            cand = (root_r / p).resolve()
        else:
            cand = p.resolve()
        try:
            rel = cand.relative_to(root_r)
        except ValueError:
            return [], f"path_outside_repo:{raw}"
        # no .. after resolve
        rel_s = str(rel).replace("\\", "/")
        if rel_s.startswith("../") or rel_s == "..":
            return [], f"path_escape:{raw}"
        out.append(rel_s)
    return out, None


def _trace(decision_trace: Any, action: str, result: GitResult) -> None:
    if decision_trace is None:
        return
    try:
        from decision_trace import TracePhase

        decision_trace.add(
            TracePhase.EXECUTION,
            f"git_ops_{action}",
            {
                "ok": result.ok,
                "message": result.message[:160],
                "dry_run": result.dry_run,
                "root": result.root[:200],
                "meta": {
                    k: result.meta.get(k)
                    for k in ("paths", "sha", "files", "staged")
                    if k in (result.meta or {})
                },
            },
        )
    except Exception:
        pass


def _require_git_and_root(
    root: Path | str | None,
) -> tuple[Path | None, GitResult | None]:
    if not git_ops_enabled():
        return None, GitResult(
            ok=False, action="disabled", message="ISAAC_GIT_OPS disabled"
        )
    if not _git_bin():
        return None, GitResult(ok=False, action="git", message="git_not_found")
    repo = find_repo_root(root)
    if not repo:
        return None, GitResult(
            ok=False,
            action="repo",
            message="not_a_git_repo",
            root=str(root or ""),
        )
    return repo, None


def git_status(
    root: Path | str | None = None,
    *,
    decision_trace: Any | None = None,
) -> GitResult:
    repo, err = _require_git_and_root(root)
    if err:
        return err
    assert repo is not None
    code, out, err_s = _run_git(repo, ["status", "--porcelain=v1", "-b"])
    result = GitResult(
        ok=code == 0,
        action="status",
        message="ok" if code == 0 else (err_s or "status_failed"),
        stdout=out,
        stderr=err_s,
        root=str(repo),
        meta={"dirty": bool(out.strip() and code == 0)},
    )
    _trace(decision_trace, "status", result)
    return result


def git_diff(
    root: Path | str | None = None,
    *,
    paths: Sequence[str] | None = None,
    staged: bool = False,
    decision_trace: Any | None = None,
    max_chars: int = 12_000,
) -> GitResult:
    repo, err = _require_git_and_root(root)
    if err:
        return err
    assert repo is not None
    norm, perr = _normalize_paths(repo, paths)
    if perr:
        return GitResult(ok=False, action="diff", message=perr, root=str(repo))
    args: list[str] = ["diff"]
    if staged:
        args.append("--cached")
    args.append("--")
    args.extend(norm)
    code, out, err_s = _run_git(repo, args)
    if len(out) > max_chars:
        out = out[:max_chars] + f"\n... [truncated {len(out) - max_chars} chars]\n"
    result = GitResult(
        ok=code == 0,
        action="diff",
        message="ok" if code == 0 else (err_s or "diff_failed"),
        stdout=out,
        stderr=err_s,
        root=str(repo),
        meta={"staged": staged, "paths": norm, "chars": len(out)},
    )
    _trace(decision_trace, "diff", result)
    return result


def git_commit(
    message: str,
    *,
    paths: Sequence[str] | None = None,
    root: Path | str | None = None,
    dry_run: bool | None = None,
    decision_trace: Any | None = None,
    skip_constitution: bool = False,
    allow_all_tracked: bool = False,
) -> GitResult:
    """Stage paths (or all modified tracked if allow_all_tracked) and commit.

    ``message`` may be LLM-authored; Isaac always invokes git commit.
    Does not push. Refuses empty message and empty path set without allow_all_tracked.
    """
    if dry_run is None:
        dry_run = git_ops_dry_run()

    repo, err = _require_git_and_root(root)
    if err:
        return err
    assert repo is not None

    msg = (message or "").strip()
    if not msg:
        return GitResult(
            ok=False, action="commit", message="empty_commit_message", root=str(repo)
        )
    # single-line safety: first line only, cap length
    msg_line = msg.splitlines()[0].strip()[:200]
    if not msg_line:
        return GitResult(
            ok=False, action="commit", message="empty_commit_message", root=str(repo)
        )

    norm, perr = _normalize_paths(repo, paths)
    if perr:
        return GitResult(ok=False, action="commit", message=perr, root=str(repo))
    if not norm and not allow_all_tracked:
        return GitResult(
            ok=False,
            action="commit",
            message="no_paths_specify_paths_or_allow_all_tracked",
            root=str(repo),
        )

    if not skip_constitution:
        allowed, blocked, warnings = _constitution_gate("commit")
        if not allowed:
            result = GitResult(
                ok=False,
                action="commit",
                message=f"constitution_blocked:{','.join(blocked)}",
                root=str(repo),
                meta={"blocked_by": blocked, "warnings": warnings},
            )
            _trace(decision_trace, "commit", result)
            return result

    if dry_run:
        # Show what would be committed
        st = git_status(repo)
        result = GitResult(
            ok=True,
            action="commit",
            message="dry_run_ok",
            stdout=st.stdout,
            dry_run=True,
            root=str(repo),
            meta={
                "paths": norm,
                "message": msg_line,
                "allow_all_tracked": allow_all_tracked,
            },
        )
        _trace(decision_trace, "commit", result)
        return result

    # Stage
    if norm:
        code, out, err_s = _run_git(repo, ["add", "--", *norm])
        if code != 0:
            result = GitResult(
                ok=False,
                action="commit",
                message=f"git_add_failed:{err_s or out}",
                stdout=out,
                stderr=err_s,
                root=str(repo),
                meta={"paths": norm},
            )
            _trace(decision_trace, "commit", result)
            return result
    else:
        # only modified tracked files — never untracked free-for-all
        code, out, err_s = _run_git(repo, ["add", "-u", "--"])
        if code != 0:
            result = GitResult(
                ok=False,
                action="commit",
                message=f"git_add_u_failed:{err_s or out}",
                stdout=out,
                stderr=err_s,
                root=str(repo),
            )
            _trace(decision_trace, "commit", result)
            return result

    # Refuse empty commit
    code, staged_diff, err_s = _run_git(repo, ["diff", "--cached", "--stat"])
    if code != 0:
        return GitResult(
            ok=False,
            action="commit",
            message="diff_cached_failed",
            stderr=err_s,
            root=str(repo),
        )
    if not (staged_diff or "").strip():
        result = GitResult(
            ok=False,
            action="commit",
            message="nothing_to_commit",
            root=str(repo),
            meta={"paths": norm},
        )
        _trace(decision_trace, "commit", result)
        return result

    code, out, err_s = _run_git(
        repo,
        [
            "commit",
            "-m",
            msg_line,
            "--no-gpg-sign",
            "--no-verify",  # avoid hanging on hooks in agent env; hooks optional later
        ],
    )
    # Note: --no-verify is pragmatic for automated agents; document as Phase-3 tradeoff
    if code != 0:
        result = GitResult(
            ok=False,
            action="commit",
            message=f"commit_failed:{err_s or out}",
            stdout=out,
            stderr=err_s,
            root=str(repo),
            meta={"paths": norm, "message": msg_line},
        )
        _trace(decision_trace, "commit", result)
        return result

    code_sha, sha_out, _ = _run_git(repo, ["rev-parse", "HEAD"])
    sha = (sha_out or "").strip() if code_sha == 0 else ""
    try:
        from audit import AuditLog

        AuditLog.action(
            "GitOps",
            "commit",
            f"sha={sha[:12]} msg={msg_line[:80]} paths={norm[:8]}",
            erfolg=True,
        )
    except Exception:
        pass

    result = GitResult(
        ok=True,
        action="commit",
        message="committed",
        stdout=out,
        stderr=err_s,
        dry_run=False,
        root=str(repo),
        meta={"paths": norm, "message": msg_line, "sha": sha},
    )
    _trace(decision_trace, "commit", result)
    return result


def git_restore(
    paths: Sequence[str],
    *,
    root: Path | str | None = None,
    dry_run: bool | None = None,
    decision_trace: Any | None = None,
    skip_constitution: bool = False,
    staged: bool = False,
) -> GitResult:
    """Discard uncommitted changes for paths (``git restore``). Not a history rewrite."""
    if dry_run is None:
        dry_run = git_ops_dry_run()

    repo, err = _require_git_and_root(root)
    if err:
        return err
    assert repo is not None

    norm, perr = _normalize_paths(repo, list(paths or []))
    if perr:
        return GitResult(ok=False, action="restore", message=perr, root=str(repo))
    if not norm:
        return GitResult(
            ok=False, action="restore", message="no_paths", root=str(repo)
        )

    if not skip_constitution:
        allowed, blocked, warnings = _constitution_gate("restore")
        if not allowed:
            result = GitResult(
                ok=False,
                action="restore",
                message=f"constitution_blocked:{','.join(blocked)}",
                root=str(repo),
                meta={"blocked_by": blocked, "warnings": warnings},
            )
            _trace(decision_trace, "restore", result)
            return result

    if dry_run:
        d = git_diff(repo, paths=norm, staged=staged)
        result = GitResult(
            ok=True,
            action="restore",
            message="dry_run_ok",
            stdout=d.stdout,
            dry_run=True,
            root=str(repo),
            meta={"paths": norm, "staged": staged},
        )
        _trace(decision_trace, "restore", result)
        return result

    # Uncommitted discard: restore worktree; optional also unstage
    if staged:
        args = ["restore", "--staged", "--worktree", "--", *norm]
    else:
        args = ["restore", "--worktree", "--", *norm]

    code, out, err_s = _run_git(repo, args)
    try:
        from audit import AuditLog

        AuditLog.action(
            "GitOps",
            "restore",
            f"paths={norm[:8]} ok={code == 0}",
            erfolg=code == 0,
        )
    except Exception:
        pass

    result = GitResult(
        ok=code == 0,
        action="restore",
        message="restored" if code == 0 else (err_s or "restore_failed"),
        stdout=out,
        stderr=err_s,
        dry_run=False,
        root=str(repo),
        meta={"paths": norm, "staged": staged},
    )
    _trace(decision_trace, "restore", result)
    return result


def format_git_result(result: GitResult, *, max_out: int = 2000) -> str:
    """Human-readable block for task.antwort."""
    lines = [
        f"[GIT:{result.action}] ok={result.ok} dry_run={result.dry_run}",
        f"  {result.message}",
    ]
    if result.meta.get("sha"):
        lines.append(f"  sha={result.meta['sha']}")
    if result.meta.get("paths"):
        lines.append(f"  paths={result.meta['paths']}")
    body = (result.stdout or "").strip()
    if body:
        lines.append(body[:max_out])
    err = (result.stderr or "").strip()
    if err and not result.ok:
        lines.append(f"stderr: {err[:500]}")
    return "\n".join(lines)


def git_ops_auto_commit_enabled() -> bool:
    """Opt-in auto-commit after successful code_edit (Phase 3.7). Default off."""
    raw = (os.environ.get("ISAAC_GIT_OPS_AUTO_COMMIT") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def parse_owner_git_command(command: str) -> dict[str, Any] | None:
    """Parse ``git status|diff|commit|restore …`` into a structured op.

    Returns None if the command should fall through to legacy shell (pull/fetch/push).
    """
    text = (command or "").strip()
    if not text.lower().startswith("git "):
        return None
    # strip leading "git "
    rest = text[4:].strip()
    if not rest:
        return None
    low = rest.lower()

    if low == "status" or low.startswith("status "):
        return {"op": "status"}

    if low == "diff" or low.startswith("diff "):
        # git diff [--cached] [paths...]
        tokens = rest.split()
        staged = False
        paths: list[str] = []
        i = 1  # skip "diff"
        while i < len(tokens):
            t = tokens[i]
            if t in {"--cached", "--staged"}:
                staged = True
            elif t.startswith("-"):
                pass  # ignore other flags for safety
            else:
                paths.append(t)
            i += 1
        return {"op": "diff", "staged": staged, "paths": paths}

    if low.startswith("commit"):
        # git commit -m "msg" [paths...]  |  git commit -m msg path
        msg = ""
        paths: list[str] = []
        m = re.search(r'-m\s+"([^"]+)"', rest)
        if m:
            msg = m.group(1).strip()
            after = rest[m.end() :].strip()
        else:
            m = re.search(r"-m\s+'([^']+)'", rest)
            if m:
                msg = m.group(1).strip()
                after = rest[m.end() :].strip()
            else:
                m = re.search(r"-m\s+(\S+)", rest)
                if m:
                    msg = m.group(1).strip()
                    after = rest[m.end() :].strip()
                else:
                    return {
                        "op": "commit",
                        "error": "commit_requires_-m_message",
                    }
        for tok in after.split():
            if tok.startswith("-"):
                continue
            paths.append(tok)
        return {"op": "commit", "message": msg, "paths": paths}

    if low.startswith("restore"):
        tokens = rest.split()[1:]  # after restore
        staged = False
        paths: list[str] = []
        for t in tokens:
            if t in {"--staged", "--worktree"}:
                if t == "--staged":
                    staged = True
                continue
            if t.startswith("-"):
                continue
            paths.append(t)
        return {"op": "restore", "paths": paths, "staged": staged}

    # pull / push / fetch / log → legacy shell (or explicit deny push later)
    return None


def run_parsed_git_op(
    parsed: dict[str, Any],
    *,
    root: Path | str | None = None,
    dry_run: bool | None = None,
    decision_trace: Any | None = None,
) -> GitResult:
    """Execute a parse_owner_git_command result via native git_ops."""
    op = str(parsed.get("op") or "")
    if parsed.get("error"):
        return GitResult(
            ok=False,
            action=op or "parse",
            message=str(parsed["error"]),
            root=str(root or ""),
        )
    if op == "status":
        return git_status(root, decision_trace=decision_trace)
    if op == "diff":
        return git_diff(
            root,
            paths=parsed.get("paths") or None,
            staged=bool(parsed.get("staged")),
            decision_trace=decision_trace,
        )
    if op == "commit":
        paths = list(parsed.get("paths") or [])
        return git_commit(
            str(parsed.get("message") or ""),
            paths=paths or None,
            root=root,
            dry_run=dry_run,
            decision_trace=decision_trace,
            allow_all_tracked=not paths,
        )
    if op == "restore":
        return git_restore(
            list(parsed.get("paths") or []),
            root=root,
            dry_run=dry_run,
            decision_trace=decision_trace,
            staged=bool(parsed.get("staged")),
        )
    return GitResult(ok=False, action=op, message="unknown_op", root=str(root or ""))
