"""Env-driven configuration for optional external memory adapters."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from config import DATA_DIR


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ExternalMemoryConfig:
    mem0_enabled: bool = False
    cognee_enabled: bool = False
    letta_enabled: bool = False
    open_interpreter_enabled: bool = False
    grok_agent_enabled: bool = False
    copilot_agent_enabled: bool = False
    write_enabled: bool = False
    min_score: float = 5.0
    search_timeout_s: float = 2.5
    write_timeout_s: float = 3.0
    search_limit: int = 4
    # Drop noisy retrieval hits below this (0–1 scale after normalize)
    search_min_score: float = 0.25
    max_hit_chars: int = 400
    owner_id: str = "Steffen"
    mem0_allow_cloud: bool = False
    mem0_api_key: str = ""
    mem0_base_url: str = "https://api.mem0.ai"
    cognee_allow_cloud: bool = False
    letta_allow_cloud: bool = False
    cognee_base_url: str = ""
    cognee_api_key: str = ""
    mem0_dir: Path = Path()
    cognee_dir: Path = Path()
    letta_bin: str = "letta"
    letta_api_key: str = ""
    letta_base_url: str = "https://api.letta.com"
    letta_agent_id: str = ""
    letta_agent_name: str = "isaac"
    letta_model: str = "openai/gpt-4o-mini"
    letta_embedding: str = "openai/text-embedding-3-small"
    open_interpreter_bin: str = "interpreter"
    open_interpreter_sandbox: str = "read-only"
    open_interpreter_provider: str = "openrouter"
    open_interpreter_model: str = "openai/gpt-4o-mini"
    open_interpreter_timeout_s: float = 180.0
    # Grok Build CLI companion (headless `grok -p`)
    grok_agent_bin: str = "grok"
    grok_agent_model: str = ""  # empty → CLI default
    grok_agent_cwd: str = ""  # empty → process cwd / repo root
    grok_agent_timeout_s: float = 300.0
    grok_agent_max_turns: int = 20
    grok_agent_always_approve: bool = False  # --always-approve / yolo
    grok_agent_safe_yolo: bool = True  # deny + safety rules when always_approve
    grok_agent_auto_resume: bool = True  # resume last session on next grok:
    grok_agent_disallowed_tools: str = ""  # comma-separated tool denylist
    grok_agent_rules: str = ""  # extra --rules guardrails
    grok_agent_extra_deny: str = ""  # extra --deny rules (comma-separated)
    # GitHub Copilot CLI / SDK / cloud agent tasks
    copilot_agent_bin: str = "copilot"
    copilot_agent_model: str = ""  # empty → CLI default / auto
    copilot_agent_cwd: str = ""
    copilot_agent_timeout_s: float = 300.0
    copilot_agent_always_approve: bool = False  # --allow-all
    copilot_agent_auto_resume: bool = True
    copilot_agent_use_sdk: bool = False  # github-copilot-sdk path
    copilot_agent_enable_memory: bool = False  # --enable-memory
    copilot_agent_allow_tools: str = ""  # comma --allow-tool=
    copilot_agent_deny_tools: str = ""  # comma --deny-tool=
    copilot_cloud_repo: str = ""  # owner/repo for CCA tasks
    copilot_cloud_base_ref: str = "main"
    copilot_cloud_create_pr: bool = False
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_llm: str = "llama3.1:8b"
    ollama_embed: str = "nomic-embed-text:latest"

    @property
    def any_enabled(self) -> bool:
        return (
            self.mem0_enabled
            or self.cognee_enabled
            or self.letta_enabled
            or self.open_interpreter_enabled
            or self.grok_agent_enabled
            or self.copilot_agent_enabled
        )


def load_external_memory_config() -> ExternalMemoryConfig:
    owner = (
        os.getenv("ISAAC_OWNER")
        or os.getenv("ISAAC_MEM0_USER_ID")
        or "Steffen"
    ).strip() or "Steffen"
    ollama_host = (
        os.getenv("OLLAMA_HOST")
        or os.getenv("ISAAC_OLLAMA_HOST")
        or "http://127.0.0.1:11434"
    ).rstrip("/")
    mem0_api_key = (
        os.getenv("MEM0_API_KEY") or os.getenv("ISAAC_MEM0_API_KEY") or ""
    ).strip()
    # Auto-enable platform path when API key present (unless explicitly disabled)
    mem0_key_present = bool(mem0_api_key)
    mem0_enabled = _env_bool("ISAAC_MEM0_ENABLED", mem0_key_present)
    mem0_allow_cloud = _env_bool("ISAAC_MEM0_ALLOW_CLOUD", mem0_key_present)
    # Writes: on by default when platform key is configured
    write_enabled = _env_bool(
        "ISAAC_EXTERNAL_MEMORY_WRITE",
        mem0_key_present,
    )
    return ExternalMemoryConfig(
        mem0_enabled=mem0_enabled,
        cognee_enabled=_env_bool("ISAAC_COGNEE_ENABLED", False),
        letta_enabled=_env_bool("ISAAC_LETTA_ENABLED", False),
        open_interpreter_enabled=_env_bool("ISAAC_OPEN_INTERPRETER_ENABLED", False),
        grok_agent_enabled=_env_bool("ISAAC_GROK_AGENT_ENABLED", False),
        copilot_agent_enabled=_env_bool("ISAAC_COPILOT_AGENT_ENABLED", False),
        write_enabled=write_enabled,
        min_score=_env_float("ISAAC_EXTERNAL_MEMORY_MIN_SCORE", 5.0),
        search_timeout_s=max(
            0.5, min(60.0, _env_float("ISAAC_EXTERNAL_MEMORY_SEARCH_TIMEOUT", 2.5))
        ),
        write_timeout_s=max(
            0.5, min(60.0, _env_float("ISAAC_EXTERNAL_MEMORY_WRITE_TIMEOUT", 3.0))
        ),
        search_limit=max(1, min(12, _env_int("ISAAC_EXTERNAL_MEMORY_SEARCH_LIMIT", 4))),
        search_min_score=max(
            0.0, min(1.0, _env_float("ISAAC_EXTERNAL_MEMORY_SEARCH_MIN_SCORE", 0.25))
        ),
        max_hit_chars=max(80, min(2000, _env_int("ISAAC_EXTERNAL_MEMORY_MAX_HIT_CHARS", 400))),
        owner_id=owner,
        mem0_allow_cloud=mem0_allow_cloud,
        mem0_api_key=mem0_api_key,
        mem0_base_url=(
            os.getenv("MEM0_BASE_URL")
            or os.getenv("ISAAC_MEM0_BASE_URL")
            or "https://api.mem0.ai"
        ).strip().rstrip("/")
        or "https://api.mem0.ai",
        cognee_allow_cloud=_env_bool("ISAAC_COGNEE_ALLOW_CLOUD", False),
        letta_allow_cloud=_env_bool("ISAAC_LETTA_ALLOW_CLOUD", False),
        cognee_base_url=(
            os.getenv("COGNEE_BASE_URL") or os.getenv("ISAAC_COGNEE_BASE_URL") or ""
        ).strip().rstrip("/"),
        cognee_api_key=(
            os.getenv("COGNEE_API_KEY") or os.getenv("ISAAC_COGNEE_API_KEY") or ""
        ).strip(),
        mem0_dir=Path(os.getenv("ISAAC_MEM0_DIR") or (DATA_DIR / "mem0")),
        cognee_dir=Path(os.getenv("ISAAC_COGNEE_DIR") or (DATA_DIR / "cognee")),
        letta_bin=(os.getenv("LETTA_BIN") or "letta").strip() or "letta",
        letta_api_key=(
            os.getenv("LETTA_API_KEY") or os.getenv("ISAAC_LETTA_API_KEY") or ""
        ).strip(),
        letta_base_url=(
            os.getenv("LETTA_BASE_URL")
            or os.getenv("ISAAC_LETTA_BASE_URL")
            or "https://api.letta.com"
        ).strip().rstrip("/")
        or "https://api.letta.com",
        letta_agent_id=(
            os.getenv("LETTA_AGENT_ID") or os.getenv("ISAAC_LETTA_AGENT_ID") or ""
        ).strip(),
        letta_agent_name=(
            os.getenv("LETTA_AGENT_NAME") or os.getenv("ISAAC_LETTA_AGENT_NAME") or "isaac"
        ).strip()
        or "isaac",
        letta_model=(
            os.getenv("LETTA_MODEL") or os.getenv("ISAAC_LETTA_MODEL") or "openai/gpt-4o-mini"
        ).strip()
        or "openai/gpt-4o-mini",
        letta_embedding=(
            os.getenv("LETTA_EMBEDDING")
            or os.getenv("ISAAC_LETTA_EMBEDDING")
            or "openai/text-embedding-3-small"
        ).strip()
        or "openai/text-embedding-3-small",
        open_interpreter_bin=(
            os.getenv("OPEN_INTERPRETER_BIN")
            or os.getenv("ISAAC_OPEN_INTERPRETER_BIN")
            or "interpreter"
        ).strip()
        or "interpreter",
        open_interpreter_sandbox=(
            os.getenv("ISAAC_OPEN_INTERPRETER_SANDBOX") or "read-only"
        ).strip()
        or "read-only",
        open_interpreter_provider=(
            os.getenv("ISAAC_OPEN_INTERPRETER_PROVIDER") or "openrouter"
        ).strip()
        or "openrouter",
        open_interpreter_model=(
            os.getenv("ISAAC_OPEN_INTERPRETER_MODEL") or "openai/gpt-4o-mini"
        ).strip()
        or "openai/gpt-4o-mini",
        open_interpreter_timeout_s=_env_float(
            "ISAAC_OPEN_INTERPRETER_TIMEOUT", 180.0
        ),
        grok_agent_bin=(
            os.getenv("GROK_BIN")
            or os.getenv("ISAAC_GROK_AGENT_BIN")
            or "grok"
        ).strip()
        or "grok",
        grok_agent_model=(
            os.getenv("ISAAC_GROK_AGENT_MODEL") or os.getenv("GROK_MODEL") or ""
        ).strip(),
        grok_agent_cwd=(
            os.getenv("ISAAC_GROK_AGENT_CWD") or ""
        ).strip(),
        grok_agent_timeout_s=_env_float("ISAAC_GROK_AGENT_TIMEOUT", 300.0),
        grok_agent_max_turns=max(1, _env_int("ISAAC_GROK_AGENT_MAX_TURNS", 20)),
        grok_agent_always_approve=_env_bool(
            "ISAAC_GROK_AGENT_ALWAYS_APPROVE", False
        ),
        grok_agent_safe_yolo=_env_bool("ISAAC_GROK_AGENT_SAFE_YOLO", True),
        grok_agent_auto_resume=_env_bool("ISAAC_GROK_AGENT_AUTO_RESUME", True),
        grok_agent_disallowed_tools=(
            os.getenv("ISAAC_GROK_AGENT_DISALLOWED_TOOLS") or ""
        ).strip(),
        grok_agent_rules=(os.getenv("ISAAC_GROK_AGENT_RULES") or "").strip(),
        grok_agent_extra_deny=(
            os.getenv("ISAAC_GROK_AGENT_EXTRA_DENY") or ""
        ).strip(),
        copilot_agent_bin=(
            os.getenv("COPILOT_BIN")
            or os.getenv("ISAAC_COPILOT_AGENT_BIN")
            or "copilot"
        ).strip()
        or "copilot",
        copilot_agent_model=(
            os.getenv("ISAAC_COPILOT_AGENT_MODEL") or os.getenv("COPILOT_MODEL") or ""
        ).strip(),
        copilot_agent_cwd=(os.getenv("ISAAC_COPILOT_AGENT_CWD") or "").strip(),
        copilot_agent_timeout_s=_env_float("ISAAC_COPILOT_AGENT_TIMEOUT", 300.0),
        copilot_agent_always_approve=_env_bool(
            "ISAAC_COPILOT_AGENT_ALWAYS_APPROVE", False
        ),
        copilot_agent_auto_resume=_env_bool("ISAAC_COPILOT_AGENT_AUTO_RESUME", True),
        copilot_agent_use_sdk=_env_bool("ISAAC_COPILOT_AGENT_USE_SDK", False),
        copilot_agent_enable_memory=_env_bool(
            "ISAAC_COPILOT_AGENT_ENABLE_MEMORY", False
        ),
        copilot_agent_allow_tools=(
            os.getenv("ISAAC_COPILOT_AGENT_ALLOW_TOOLS") or ""
        ).strip(),
        copilot_agent_deny_tools=(
            os.getenv("ISAAC_COPILOT_AGENT_DENY_TOOLS") or ""
        ).strip(),
        copilot_cloud_repo=(
            os.getenv("ISAAC_COPILOT_CLOUD_REPO") or ""
        ).strip(),
        copilot_cloud_base_ref=(
            os.getenv("ISAAC_COPILOT_CLOUD_BASE_REF") or "main"
        ).strip()
        or "main",
        copilot_cloud_create_pr=_env_bool("ISAAC_COPILOT_CLOUD_CREATE_PR", False),
        ollama_host=ollama_host,
        ollama_llm=(
            os.getenv("ISAAC_MEM0_OLLAMA_MODEL")
            or os.getenv("OLLAMA_MODEL")
            or "llama3.1:8b"
        ).strip(),
        ollama_embed=(
            os.getenv("ISAAC_MEM0_EMBED_MODEL")
            or "nomic-embed-text:latest"
        ).strip(),
    )
