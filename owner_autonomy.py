"""Isaac – Proaktive Owner-Autonomie (nur ISAAC_PRIVILEGE_MODE=admin)

Führt geplante Owner-Befehle im Background-Loop aus (z. B. nächtliches Cleanup),
wenn Zeitfenster, Akku und Intervall es erlauben.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Optional

from audit import AuditLog
from config import RUNTIME_SETTINGS_PATH, is_owner_equivalent_mode

log = logging.getLogger("Isaac.OwnerAutonomy")

_TASK_ENV_ALIASES: dict[str, str] = {
    "nightly_downloads_cleanup": "NIGHTLY",
    "weekly_deep_cleanup": "WEEKLY",
    "daily_isaac_health": "HEALTH",
}

_WEEKDAY_ALIASES: dict[str, int] = {
    "mon": 0,
    "mo": 0,
    "monday": 0,
    "montag": 0,
    "tue": 1,
    "di": 1,
    "tuesday": 1,
    "dienstag": 1,
    "wed": 2,
    "mi": 2,
    "wednesday": 2,
    "mittwoch": 2,
    "thu": 3,
    "do": 3,
    "thursday": 3,
    "donnerstag": 3,
    "fri": 4,
    "fr": 4,
    "friday": 4,
    "freitag": 4,
    "sat": 5,
    "sa": 5,
    "saturday": 5,
    "samstag": 5,
    "sun": 6,
    "so": 6,
    "sunday": 6,
    "sonntag": 6,
}


def owner_autonomy_enabled() -> bool:
    if not is_owner_equivalent_mode():
        return False
    raw = str(os.getenv("ISAAC_OWNER_AUTONOMY", "1") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ScheduledOwnerTask:
    task_id: str
    action_kind: str
    params: dict[str, Any] = field(default_factory=dict)
    raw_phrase: str = ""
    window_start_hour: int = 2
    window_end_hour: int = 5
    min_interval_hours: float = 20.0
    requires_plugged: bool = True
    min_battery_percent: int = 35
    weekday: Optional[int] = None  # 0=Mo … 6=So; None = jeden Tag


DEFAULT_SCHEDULED_OWNER_TASKS: tuple[ScheduledOwnerTask, ...] = (
    ScheduledOwnerTask(
        task_id="nightly_downloads_cleanup",
        action_kind="filesystem_cleanup",
        params={"scope": "standard", "dry_run": False, "root": "~/Downloads"},
        raw_phrase="räume downloads auf",
        window_start_hour=2,
        window_end_hour=5,
        min_interval_hours=20.0,
        requires_plugged=True,
        min_battery_percent=40,
    ),
    ScheduledOwnerTask(
        task_id="weekly_deep_cleanup",
        action_kind="filesystem_cleanup",
        params={"scope": "deep", "dry_run": False},
        raw_phrase="räume mein dateisystem auf",
        window_start_hour=3,
        window_end_hour=5,
        min_interval_hours=160.0,
        requires_plugged=True,
        min_battery_percent=55,
        weekday=6,
    ),
    ScheduledOwnerTask(
        task_id="daily_isaac_health",
        action_kind="isaac_ops",
        params={"op": "status"},
        raw_phrase="isaac status",
        window_start_hour=6,
        window_end_hour=23,
        min_interval_hours=12.0,
        requires_plugged=False,
        min_battery_percent=30,
    ),
    ScheduledOwnerTask(
        task_id="weekly_toolkit_sync",
        action_kind="security_toolkit",
        params={"action": "sync", "install_missing": True},
        raw_phrase="sync security toolkit",
        window_start_hour=4,
        window_end_hour=6,
        min_interval_hours=160.0,
        requires_plugged=True,
        min_battery_percent=50,
        weekday=0,
    ),
)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_weekday(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 6 else None
    raw = str(value).strip().lower()
    if raw.isdigit():
        day = int(raw)
        return day if 0 <= day <= 6 else None
    return _WEEKDAY_ALIASES.get(raw)


def _clamp_hour(value: Any, default: int) -> int:
    try:
        hour = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(23, hour))


def _load_runtime_owner_autonomy_config() -> dict[str, Any]:
    if not RUNTIME_SETTINGS_PATH.exists():
        return {}
    try:
        raw = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("Owner-Autonomie runtime_settings: %s", exc)
        return {}
    section = raw.get("owner_autonomy")
    return section if isinstance(section, dict) else {}


def _merge_task_config(task: ScheduledOwnerTask, cfg: dict[str, Any]) -> ScheduledOwnerTask:
    if not cfg:
        return task

    params = dict(task.params)
    if isinstance(cfg.get("params"), dict):
        params.update(cfg["params"])

    weekday = task.weekday
    if "weekday" in cfg:
        weekday = _parse_weekday(cfg.get("weekday"))

    return replace(
        task,
        params=params,
        raw_phrase=str(cfg.get("raw_phrase") or task.raw_phrase),
        window_start_hour=_clamp_hour(cfg.get("window_start_hour"), task.window_start_hour),
        window_end_hour=_clamp_hour(cfg.get("window_end_hour"), task.window_end_hour),
        min_interval_hours=float(cfg.get("min_interval_hours", task.min_interval_hours)),
        requires_plugged=bool(cfg.get("requires_plugged", task.requires_plugged)),
        min_battery_percent=int(cfg.get("min_battery_percent", task.min_battery_percent)),
        weekday=weekday,
    )


def _apply_env_task_overrides(task: ScheduledOwnerTask) -> Optional[ScheduledOwnerTask]:
    alias = _TASK_ENV_ALIASES.get(task.task_id, task.task_id.upper())
    prefix = f"ISAAC_OWNER_AUTONOMY_{alias}_"

    enabled = os.getenv(f"{prefix}ENABLED")
    if enabled is not None and not _truthy(enabled):
        return None

    updates: dict[str, Any] = {}
    if os.getenv(f"{prefix}START") is not None:
        updates["window_start_hour"] = _clamp_hour(os.getenv(f"{prefix}START"), task.window_start_hour)
    if os.getenv(f"{prefix}END") is not None:
        updates["window_end_hour"] = _clamp_hour(os.getenv(f"{prefix}END"), task.window_end_hour)
    if os.getenv(f"{prefix}INTERVAL_HOURS") is not None:
        try:
            updates["min_interval_hours"] = float(os.getenv(f"{prefix}INTERVAL_HOURS"))
        except (TypeError, ValueError):
            pass
    if os.getenv(f"{prefix}PLUGGED") is not None:
        updates["requires_plugged"] = _truthy(os.getenv(f"{prefix}PLUGGED"))
    if os.getenv(f"{prefix}MIN_BATTERY") is not None:
        try:
            updates["min_battery_percent"] = max(0, min(100, int(os.getenv(f"{prefix}MIN_BATTERY"))))
        except (TypeError, ValueError):
            pass
    if os.getenv(f"{prefix}DAY") is not None:
        updates["weekday"] = _parse_weekday(os.getenv(f"{prefix}DAY"))

    return replace(task, **updates) if updates else task


def get_scheduled_owner_tasks() -> tuple[ScheduledOwnerTask, ...]:
    """Lädt Standard-Tasks mit Overrides aus runtime_settings.json und .env."""
    runtime = _load_runtime_owner_autonomy_config()
    runtime_tasks = runtime.get("tasks") if isinstance(runtime.get("tasks"), dict) else {}
    if runtime.get("enabled") is False:
        return ()

    resolved: list[ScheduledOwnerTask] = []
    for task in DEFAULT_SCHEDULED_OWNER_TASKS:
        cfg = runtime_tasks.get(task.task_id)
        if isinstance(cfg, dict) and cfg.get("enabled") is False:
            continue
        merged = _merge_task_config(task, cfg if isinstance(cfg, dict) else {})
        env_task = _apply_env_task_overrides(merged)
        if env_task is not None:
            resolved.append(env_task)
    return tuple(resolved)


# Abwärtskompatibilität
SCHEDULED_OWNER_TASKS = DEFAULT_SCHEDULED_OWNER_TASKS


def _in_hour_window(hour: int, start: int, end: int) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _hours_since(task_id: str, last_runs: dict[str, str]) -> float:
    raw = (last_runs or {}).get(task_id)
    if not raw:
        return float("inf")
    try:
        last = datetime.fromisoformat(raw)
    except ValueError:
        return float("inf")
    delta = datetime.now() - last
    return max(0.0, delta.total_seconds() / 3600.0)


def due_owner_tasks(
    *,
    last_runs: dict[str, str],
    akku: dict[str, Any],
    now: Optional[datetime] = None,
) -> list[ScheduledOwnerTask]:
    """Gibt fällige, aber noch nicht ausgeführte Owner-Tasks zurück."""
    if not owner_autonomy_enabled():
        return []

    current = now or datetime.now()
    hour = current.hour
    weekday = current.weekday()
    plugged = bool(akku.get("plugged", True))
    battery = int(akku.get("prozent", 100) or 100)

    due: list[ScheduledOwnerTask] = []
    for task in get_scheduled_owner_tasks():
        if task.requires_plugged and not plugged:
            continue
        if battery < task.min_battery_percent:
            continue
        if task.weekday is not None and weekday != task.weekday:
            continue
        if not _in_hour_window(hour, task.window_start_hour, task.window_end_hour):
            continue
        if _hours_since(task.task_id, last_runs) < task.min_interval_hours:
            continue
        due.append(task)
    return due


async def run_due_owner_autonomy_tasks(
    *,
    last_runs: dict[str, str],
    akku: dict[str, Any],
    on_note: Optional[Callable[[str], None]] = None,
    now: Optional[datetime] = None,
) -> dict[str, str]:
    """Führt fällige Owner-Tasks aus und aktualisiert last_runs."""
    if not owner_autonomy_enabled():
        return dict(last_runs or {})

    from owner_action import OwnerAction, execute_owner_action
    from procedure_memory import record_owner_action_outcome

    updated = dict(last_runs or {})
    current = now or datetime.now()

    for task in due_owner_tasks(last_runs=updated, akku=akku, now=current):
        action = OwnerAction(task.action_kind, dict(task.params), raw=task.raw_phrase)
        try:
            if task.action_kind == "security_toolkit":
                from security_toolkit import execute_security_command

                result, ok = await execute_security_command(dict(task.params))
            else:
                result, ok = await execute_owner_action(action)
        except Exception as exc:
            log.warning("Owner-Autonomie %s fehlgeschlagen: %s", task.task_id, exc)
            result, ok = f"[Owner-Autonomie] Fehler: {exc}", False

        try:
            record_owner_action_outcome(kind=task.action_kind, raw=task.raw_phrase, ok=ok)
        except Exception as exc:
            log.debug("Owner procedure capture skipped: %s", exc)

        updated[task.task_id] = current.isoformat(timespec="seconds")
        summary = (result or "").replace("\n", " ")[:160]
        note = f"[Owner-Autonomie] {task.task_id}: {'OK' if ok else 'FAIL'} — {summary}"
        if on_note:
            on_note(note)
        AuditLog.action(
            "OwnerAutonomy",
            task.task_id,
            f"ok={ok} kind={task.action_kind} phrase={task.raw_phrase[:80]}",
        )
        log.info("Owner-Autonomie ausgeführt: %s ok=%s", task.task_id, ok)

    return updated