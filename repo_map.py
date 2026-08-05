"""Native RepoMap for Isaac (Aider-inspired pattern — not a wholesale import).

BLAU-layer: builds a ranked, token-budgeted code context from the local tree.
Control stays with ROT (who calls, for which intent); Executor never ranks.

Phase 1.1 decisions
-------------------
API
    get_ranked_context(task, max_tokens=..., root=...) -> RankedContext

Backend (v1)
    stdlib ``ast`` for Python only. Always available, no new default deps.
    Optional tree-sitter / PageRank (networkx) may land later behind flags —
    never required for the kernel to stay runnable.

Hook (Phase 1.7, not wired here)
    Enrich in ``IsaacKernel._retrieve_relevant_context`` when intent is CODE
    (optional FILE later), via ``maybe_enrich_retrieval_with_repo_map``.
    Result lands on the existing retrieval dict as ``code_map`` (+ meta),
    then ``format_retrieval_context`` emits a ``[code_map]`` section.
    Not a second retrieval path; not inside executor._execute_code alone.

Env
    ISAAC_REPO_MAP=0 disables building (default: enabled when called).
    ISAAC_REPO_MAP_MAX_TOKENS overrides default budget (default 1024).
    ISAAC_REPO_MAP_ROOT optional absolute root (default: config.BASE_DIR).

Do-NOT
    Import aider package; default tree-sitter-language-pack; second memory path;
    silent repo writes (Phase 2).
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_MAX_TOKENS = 1024
DEFAULT_MAX_FILES = 120
DEFAULT_MAX_FILE_BYTES = 400_000
# ~4 chars per token — coarse, model-agnostic (Aider uses real model counts).
CHARS_PER_TOKEN = 4.0

_EXCLUDE_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        ".eggs",
        ".aider.tags.cache.v4",
        "chroma",
        "traces",
        "logs",
        "data",
        "workspace",
        ".isaac_exec",
    }
)

_EXCLUDE_PATH_PARTS = frozenset(
    {
        "site-packages",
        ".grok",
    }
)


@dataclass(frozen=True)
class SymbolTag:
    """One definition extracted from a source file."""

    rel_path: str
    name: str
    kind: str  # class | function | method | async_function
    line: int
    signature: str
    parent: str = ""


@dataclass(frozen=True)
class RankedContext:
    """Result of get_ranked_context — text for prompts + inspectable meta."""

    text: str
    files: tuple[str, ...]
    n_symbols: int
    token_estimate: int
    backend: str
    root: str
    enabled: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "files": list(self.files),
            "n_symbols": self.n_symbols,
            "token_estimate": self.token_estimate,
            "backend": self.backend,
            "root": self.root,
            "enabled": self.enabled,
            "meta": dict(self.meta),
        }


def repo_map_enabled() -> bool:
    raw = (os.environ.get("ISAAC_REPO_MAP") or "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def default_root() -> Path:
    env_root = (os.environ.get("ISAAC_REPO_MAP_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    try:
        from config import BASE_DIR

        return Path(BASE_DIR).resolve()
    except Exception:
        return Path.cwd().resolve()


def default_max_tokens() -> int:
    raw = (os.environ.get("ISAAC_REPO_MAP_MAX_TOKENS") or "").strip()
    if raw.isdigit():
        return max(64, min(int(raw), 16_000))
    return DEFAULT_MAX_TOKENS


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def _task_terms(task: str) -> list[str]:
    terms = [w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", task or "") if len(w) >= 3]
    # Prefer longer / more distinctive tokens first
    uniq: list[str] = []
    seen: set[str] = set()
    for t in sorted(terms, key=lambda x: (-len(x), x.lower())):
        low = t.lower()
        if low in seen:
            continue
        seen.add(low)
        uniq.append(low)
        if len(uniq) >= 24:
            break
    return uniq


def _should_skip_dir(name: str) -> bool:
    return name in _EXCLUDE_DIR_NAMES or name.startswith(".")


def _iter_python_files(root: Path, max_files: int = DEFAULT_MAX_FILES) -> list[Path]:
    out: list[Path] = []
    root = root.resolve()
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        # prune in-place
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not _should_skip_dir(d)
            and d not in _EXCLUDE_PATH_PARTS
        )
        rel_dir = Path(dirpath).resolve().relative_to(root)
        parts = set(rel_dir.parts) if str(rel_dir) != "." else set()
        if parts & _EXCLUDE_PATH_PARTS:
            dirnames[:] = []
            continue
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            if name.startswith("."):
                continue
            path = Path(dirpath) / name
            try:
                if path.stat().st_size > DEFAULT_MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            out.append(path)
            if len(out) >= max_files:
                return out
    return out


def _sig_from_function(node: ast.AST, name: str, kind: str) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"{kind} {name}"
    args = node.args
    parts: list[str] = []
    for a in args.posonlyargs:
        parts.append(a.arg)
    if args.posonlyargs:
        parts.append("/")
    for a in args.args:
        parts.append(a.arg)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")
    for a in args.kwonlyargs:
        parts.append(a.arg)
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {name}({', '.join(parts)})"


def extract_python_tags(abs_path: Path, rel_path: str) -> list[SymbolTag]:
    """stdlib-ast definitions for one Python file (fail-soft)."""
    try:
        src = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        tree = ast.parse(src, filename=str(abs_path))
    except SyntaxError:
        return []

    tags: list[SymbolTag] = []

    def walk(nodes: Iterable[ast.AST], parent: str = "") -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                tags.append(
                    SymbolTag(
                        rel_path=rel_path,
                        name=node.name,
                        kind="class",
                        line=getattr(node, "lineno", 0) or 0,
                        signature=f"class {node.name}",
                        parent=parent,
                    )
                )
                walk(node.body, parent=node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = (
                    "method"
                    if parent
                    else (
                        "async_function"
                        if isinstance(node, ast.AsyncFunctionDef)
                        else "function"
                    )
                )
                tags.append(
                    SymbolTag(
                        rel_path=rel_path,
                        name=node.name,
                        kind=kind,
                        line=getattr(node, "lineno", 0) or 0,
                        signature=_sig_from_function(node, node.name, kind),
                        parent=parent,
                    )
                )
            # Do not recurse into function bodies for nested defs (keep map shallow)

    walk(tree.body)
    return tags


def _file_score(
    rel_path: str,
    tags: list[SymbolTag],
    terms: Sequence[str],
    chat_files: set[str],
    mentioned: set[str],
) -> float:
    score = 0.0
    path_l = rel_path.lower().replace("\\", "/")
    base = Path(rel_path).stem.lower()

    if rel_path in chat_files or path_l in chat_files:
        score += 50.0
    for m in mentioned:
        if m and m in path_l:
            score += 20.0

    for term in terms:
        if term in path_l:
            score += 8.0
        if term == base or term in base:
            score += 6.0
        for tag in tags:
            name_l = tag.name.lower()
            if term == name_l:
                score += 12.0
            elif term in name_l:
                score += 4.0
            if term in tag.signature.lower():
                score += 2.0

    # Mild centrality proxy: more public-ish symbols → slightly higher
    score += min(len(tags), 20) * 0.15
    # Prefer non-test modules slightly when terms match elsewhere equally
    if "test" in path_l or path_l.startswith("tests"):
        score *= 0.85
    return score


def _symbol_score(tag: SymbolTag, terms: Sequence[str], file_score: float) -> float:
    s = file_score
    name_l = tag.name.lower()
    for term in terms:
        if term == name_l:
            s += 15.0
        elif term in name_l:
            s += 5.0
    if tag.kind == "class":
        s += 1.5
    if tag.name.startswith("_") and not tag.name.startswith("__"):
        s -= 2.0
    return s


def _render_map(
    ranked: list[tuple[float, SymbolTag]],
    max_tokens: int,
) -> tuple[str, list[str], int]:
    """Group by file, emit Aider-like outline until token budget."""
    by_file: dict[str, list[tuple[float, SymbolTag]]] = {}
    order: list[str] = []
    for sc, tag in ranked:
        if tag.rel_path not in by_file:
            by_file[tag.rel_path] = []
            order.append(tag.rel_path)
        by_file[tag.rel_path].append((sc, tag))

    lines: list[str] = []
    used_files: list[str] = []
    budget_chars = max(256, int(max_tokens * CHARS_PER_TOKEN))

    for rel in order:
        block = [f"{rel}:"]
        # sort symbols in file by score desc, then line
        for sc, tag in sorted(by_file[rel], key=lambda x: (-x[0], x[1].line, x[1].name)):
            indent = "    " if tag.parent else "  "
            if tag.parent:
                block.append(f"{indent}{tag.signature}  # in {tag.parent}")
            else:
                block.append(f"{indent}{tag.signature}")
        candidate = "\n".join(block)
        trial = ("\n".join(lines) + ("\n" if lines else "") + candidate).strip()
        if estimate_tokens(trial) > max_tokens and lines:
            break
        lines.append(candidate)
        used_files.append(rel)
        if len("\n".join(lines)) >= budget_chars:
            break

    text = "\n".join(lines).strip()
    return text, used_files, estimate_tokens(text)


def get_ranked_context(
    task: str,
    *,
    max_tokens: int | None = None,
    root: Path | str | None = None,
    chat_files: Sequence[str] | None = None,
    mentioned: Sequence[str] | None = None,
    max_files: int = DEFAULT_MAX_FILES,
    enabled: bool | None = None,
) -> RankedContext:
    """Build a ranked code map for *task* within token budget.

    Parameters
    ----------
    task:
        Natural-language task / user input (used for personalization).
    max_tokens:
        Soft budget for returned map text (char/4 estimate).
    root:
        Repo root to scan (default BASE_DIR / ISAAC_REPO_MAP_ROOT).
    chat_files:
        Files already in focus (boost ranking — Aider personalization idea).
    mentioned:
        Path fragments or symbol names mentioned in chat.
    """
    if enabled is None:
        enabled = repo_map_enabled()
    root_path = Path(root).expanduser().resolve() if root else default_root()
    tokens = max_tokens if max_tokens is not None else default_max_tokens()
    tokens = max(64, min(int(tokens), 16_000))

    empty_meta = {
        "n_files_scanned": 0,
        "n_tags": 0,
        "terms": [],
        "reason": "",
    }

    if not enabled:
        return RankedContext(
            text="",
            files=(),
            n_symbols=0,
            token_estimate=0,
            backend="disabled",
            root=str(root_path),
            enabled=False,
            meta={**empty_meta, "reason": "ISAAC_REPO_MAP disabled"},
        )

    terms = _task_terms(task)
    chat_set = {str(x).replace("\\", "/") for x in (chat_files or []) if x}
    ment_set = {str(x).lower() for x in (mentioned or []) if x}

    py_files = _iter_python_files(root_path, max_files=max_files)
    all_tags: list[SymbolTag] = []
    file_tags: dict[str, list[SymbolTag]] = {}
    for abs_path in py_files:
        try:
            rel = str(abs_path.resolve().relative_to(root_path)).replace("\\", "/")
        except ValueError:
            rel = abs_path.name
        tags = extract_python_tags(abs_path, rel)
        if not tags:
            continue
        file_tags[rel] = tags
        all_tags.extend(tags)

    if not all_tags:
        return RankedContext(
            text="",
            files=(),
            n_symbols=0,
            token_estimate=0,
            backend="stdlib_ast",
            root=str(root_path),
            enabled=True,
            meta={
                **empty_meta,
                "n_files_scanned": len(py_files),
                "reason": "no_symbols",
            },
        )

    file_scores = {
        rel: _file_score(rel, tags, terms, chat_set, ment_set)
        for rel, tags in file_tags.items()
    }

    scored: list[tuple[float, SymbolTag]] = []
    for tag in all_tags:
        scored.append((_symbol_score(tag, terms, file_scores.get(tag.rel_path, 0.0)), tag))
    scored.sort(key=lambda x: (-x[0], x[1].rel_path, x[1].line, x[1].name))

    text, used_files, tok_est = _render_map(scored, tokens)
    n_sym = 0
    used_set = set(used_files)
    for sc, tag in scored:
        if tag.rel_path in used_set:
            # Count symbols that appear in the rendered text
            if tag.signature in text or tag.name in text:
                n_sym += 1
    return RankedContext(
        text=text,
        files=tuple(used_files),
        n_symbols=n_sym,
        token_estimate=tok_est,
        backend="stdlib_ast",
        root=str(root_path),
        enabled=True,
        meta={
            "n_files_scanned": len(py_files),
            "n_tags": len(all_tags),
            "terms": terms[:12],
            "max_tokens": tokens,
            "reason": "ok",
        },
    )


def maybe_enrich_retrieval_with_repo_map(
    retrieval_ctx: dict[str, Any],
    *,
    user_input: str,
    intent: str = "",
    root: Path | str | None = None,
    max_tokens: int | None = None,
    decision_trace: Any | None = None,
) -> dict[str, Any]:
    """Optional BLAU enrichment helper for Phase 1.7.

    Safe to call always: no-ops when disabled, non-code intent, or on errors.
    Does not replace build_retrieval_context — only adds ``code_map`` keys.
    """
    ctx = dict(retrieval_ctx or {})
    # CODE primary only in Phase 1; FILE later if needed.
    intent_norm = str(intent or "").strip().lower()
    # Accept "code" or enum-style values ending in ".code"
    if intent_norm != "code" and not intent_norm.endswith(".code"):
        return ctx

    if not repo_map_enabled():
        return ctx

    try:
        ranked = get_ranked_context(
            user_input or ctx.get("query") or "",
            max_tokens=max_tokens,
            root=root,
        )
    except Exception as exc:
        ctx["code_map_meta"] = {"error": type(exc).__name__, "reason": "exception"}
        return ctx

    if ranked.text:
        ctx["code_map"] = ranked.text
    ctx["code_map_meta"] = {
        "files": list(ranked.files),
        "n_symbols": ranked.n_symbols,
        "token_estimate": ranked.token_estimate,
        "backend": ranked.backend,
        "root": ranked.root,
        "enabled": ranked.enabled,
        **ranked.meta,
    }

    if decision_trace is not None:
        try:
            from decision_trace import TracePhase

            decision_trace.add(
                TracePhase.RETRIEVAL,
                "repo_map_built",
                {
                    "n_files": len(ranked.files),
                    "n_symbols": ranked.n_symbols,
                    "tokens": ranked.token_estimate,
                    "backend": ranked.backend,
                    "root": ranked.root[:200],
                    "enabled": ranked.enabled,
                    "reason": ranked.meta.get("reason", ""),
                },
            )
        except Exception:
            pass

    return ctx


def format_code_map_section(retrieval_ctx: dict[str, Any] | None) -> str:
    """Render [code_map] section for format_retrieval_context integration."""
    data = retrieval_ctx or {}
    text = (data.get("code_map") or "").strip()
    if not text:
        return ""
    meta = data.get("code_map_meta") or {}
    header = "[code_map]"
    if meta.get("backend") or meta.get("token_estimate"):
        header += (
            f" backend={meta.get('backend', '?')}"
            f" tokens~{meta.get('token_estimate', '?')}"
            f" files={len(meta.get('files') or [])}"
        )
    return f"{header}\n{text}"
