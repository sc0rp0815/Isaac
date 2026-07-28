"""Optional external memory / companion adapters (Mem0, Cognee, Letta, OI, Grok, Copilot, Context7).

Opt-in via env flags. Never replaces Isaac SQLite memory ownership.
"""

from external_memory.bridge import (
    ExternalMemoryBridge,
    get_external_memory_bridge,
    reset_external_memory_bridge,
)
from external_memory.config import ExternalMemoryConfig, load_external_memory_config

__all__ = [
    "ExternalMemoryBridge",
    "ExternalMemoryConfig",
    "get_external_memory_bridge",
    "load_external_memory_config",
    "reset_external_memory_bridge",
]
