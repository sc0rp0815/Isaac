"""Isaac – Proaktive Owner-Autonomie (nur ISAAC_PRIVILEGE_MODE=admin)

Führt geplante Owner-Befehle im Background-Loop aus (z. B. nächtliches Cleanup),
wenn Zeitfenster, Akku und Intervall es erlauben.

Grenzen (E2.0+):
  - nur Admin/Owner-Modus
  - Constitution-Gate vor Ausführung
  - max. Tasks pro Zyklus
  - Failure-Backoff bei wiederholten Fehlern
  - inspectable Status (kein freies „wollen“, nur geplante Pfade)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from audit import AuditLog
from config import DATA_DIR, RUNTIME_SETTINGS_PATH, is_owner_equivalent_mode

log = logging.getLogger("Isaac.OwnerAutonomy")

AUTONOMY_STATE_PATH = DATA_DIR / "owner_autonomy_state.json"
DEFAULT_MAX_TASKS_PER_CYCLE = 2
FAILURE_BACKOFF_MULTIPLIER = 2.0
FAILURE_BACKOFF_THRESHOLD = 2

_TASK_ENV_ALIASES: dict[str, str] = {
    "nightly_downloads_cleanup": "NIGHTLY",
    "weekly_deep_cleanup": "WEEKLY",
    "daily_isaac_health": "HEALTH",
    "weekly_toolkit_sync": "TOOLKIT",
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


def max_tasks_per_cycle() -> int:
    raw = os.getenv("ISAAC_OWNER_AUTONOMY_MAX_PER_CYCLE")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_MAX_TASKS_PER_CYCLE
    try:
        return max(1, min(10, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_TASKS_PER_CYCLE


def load_autonomy_state(path: Path | None = None) -> dict[str, Any]:
    target = path or AUTONOMY_STATE_PATH
    if not target.exists():
        return {"tasks": {}}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("Owner-Autonomie-State unlesbar: %s", exc)
        return {"tasks": {}}
    if not isinstance(data, dict):
        return {"tasks": {}}
    tasks = data.get("tasks")
    if not isinstance(tasks, dict):
        data["tasks"] = {}
    return data


def save_autonomy_state(state: dict[str, Any], path: Path | None = None) -> None:
    target = path or AUTONOMY_STATE_PATH
    payload = dict(state or {})
    if "tasks" not in payload or not isinstance(payload.get("tasks"), dict):
        payload["tasks"] = {}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass


def _task_failure_count(state: dict[str, Any], task_id: str) -> int:
    row = (state.get("tasks") or {}).get(task_id) or {}
    try:
        return max(0, int(row.get("consecutive_failures") or 0))
    except (TypeError, ValueError):
        return 0


def _record_task_outcome(state: dict[str, Any], task_id: str, *, ok: bool, ts: str) -> dict[str, Any]:
    tasks = dict(state.get("tasks") or {})
    prev = dict(tasks.get(task_id) or {})
    fails = int(prev.get("consecutive_failures") or 0)
    if ok:
        fails = 0
    else:
        fails += 1
    tasks[task_id] = {
        "last_run": ts,
        "last_ok": bool(ok),
        "consecutive_failures": fails,
        "total_ok": int(prev.get("total_ok") or 0) + (1 if ok else 0),
        "total_fail": int(prev.get("total_fail") or 0) + (0 if ok else 1),
    }
    state = dict(state)
    state["tasks"] = tasks
    state["updated"] = ts
    return state


def _effective_interval_hours(task: ScheduledOwnerTask, state: dict[str, Any]) -> float:
    base = float(task.min_interval_hours)
    fails = _task_failure_count(state, task.task_id)
    if fails >= FAILURE_BACKOFF_THRESHOLD:
        return base * FAILURE_BACKOFF_MULTIPLIER
    return base


def _constitution_gate_autonomy_task(task: ScheduledOwnerTask) -> Optional[str]:
    """Verfassungs-Gate vor proaktiver Ausführung (Audit + Owner-Bound)."""
    from constitution_override import critical_action_gate

    kind = (task.action_kind or "").strip().lower()
    dry_run = bool((task.params or {}).get("dry_run"))
    if kind in {"filesystem_cleanup", "security_toolkit", "shell"}:
        action = "system_command"
        destructive = kind == "security_toolkit" or (kind == "filesystem_cleanup" and not dry_run)
    elif kind in {"file_write", "file_delete"}:
        action = "file_delete" if kind == "file_delete" else "system_command"
        destructive = True
    else:
        # status/ops: leichte high-impact-Warnung, kein destruktiver Block
        action = "tool_invoke"
        destructive = False

    return critical_action_gate(
        action,
        source=f"owner_autonomy.{task.task_id}",
        owner_approved=is_owner_equivalent_mode(),
        destructive=destructive,
        risk="high",
        extra_metadata={
            "autonomy_task": task.task_id,
            "action_kind": kind,
            "raw_phrase": (task.raw_phrase or "")[:80],
        },
    )


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
    autonomy_state: Optional[dict[str, Any]] = None,
    limit: Optional[int] = None,
) -> list[ScheduledOwnerTask]:
    """Gibt fällige, aber noch nicht ausgeführte Owner-Tasks zurück."""
    if not owner_autonomy_enabled():
        return []

    current = now or datetime.now()
    hour = current.hour
    weekday = current.weekday()
    plugged = bool(akku.get("plugged", True))
    battery = int(akku.get("prozent", 100) or 100)
    state = autonomy_state if autonomy_state is not None else load_autonomy_state()

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
        needed = _effective_interval_hours(task, state)
        if _hours_since(task.task_id, last_runs) < needed:
            continue
        due.append(task)

    # limit=None → Zyklus-Cap; limit<0 → uncapped; limit>=0 → hartes Maximum
    if limit is None:
        cap = max_tasks_per_cycle()
    else:
        cap = int(limit)
    if cap >= 0 and len(due) > cap:
        return due[:cap]
    return due


def autonomy_status(
    *,
    last_runs: Optional[dict[str, str]] = None,
    akku: Optional[dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Inspectable Status der Owner-Autonomie (für Dashboard/Status-Befehle)."""
    current = now or datetime.now()
    battery = akku if isinstance(akku, dict) else {"plugged": True, "prozent": 100}
    runs = dict(last_runs or {})
    state = load_autonomy_state()
    scheduled = get_scheduled_owner_tasks()
    due_uncapped = due_owner_tasks(
        last_runs=runs,
        akku=battery,
        now=current,
        autonomy_state=state,
        limit=-1,
    )
    due_capped = due_uncapped[: max_tasks_per_cycle()]
    return {
        "enabled": owner_autonomy_enabled(),
        "admin_mode": is_owner_equivalent_mode(),
        "max_per_cycle": max_tasks_per_cycle(),
        "now": current.isoformat(timespec="seconds"),
        "scheduled_count": len(scheduled),
        "scheduled": [
            {
                "task_id": t.task_id,
                "action_kind": t.action_kind,
                "window": f"{t.window_start_hour:02d}-{t.window_end_hour:02d}",
                "min_interval_hours": t.min_interval_hours,
                "effective_interval_hours": _effective_interval_hours(t, state),
                "requires_plugged": t.requires_plugged,
                "min_battery_percent": t.min_battery_percent,
                "weekday": t.weekday,
                "last_run": runs.get(t.task_id, ""),
                "consecutive_failures": _task_failure_count(state, t.task_id),
            }
            for t in scheduled
        ],
        "due_task_ids": [t.task_id for t in due_capped],
        "due_uncapped_count": len(due_uncapped),
        "state_path": str(AUTONOMY_STATE_PATH),
    }


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
    ts = current.isoformat(timespec="seconds")
    state = load_autonomy_state()
    executed = 0

    for task in due_owner_tasks(
        last_runs=updated,
        akku=akku,
        now=current,
        autonomy_state=state,
        limit=max_tasks_per_cycle(),
    ):
        gate_block = _constitution_gate_autonomy_task(task)
        if gate_block:
            note = f"[Owner-Autonomie] {task.task_id}: BLOCK — {gate_block}"
            if on_note:
                on_note(note)
            AuditLog.action(
                "OwnerAutonomy",
                task.task_id,
                f"blocked constitution kind={task.action_kind}",
                erfolg=False,
            )
            state = _record_task_outcome(state, task.task_id, ok=False, ts=ts)
            # Block zählt als Versuch mit Backoff, aber last_runs nur bei echten Runs?
            # Bounded: Block speichern, Intervall greifen lassen
            updated[task.task_id] = ts
            executed += 1
            continue

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

        try:
            from memory import get_memory

            get_memory().log_development_event(
                event_type="owner_autonomy_run",
                target_kind="autonomy_task",
                target_key=task.task_id,
                reason=f"{'ok' if ok else 'fail'}: {(result or '')[:120]}",
                confidence_before=0.0,
                confidence_after=1.0 if ok else 0.2,
                requires_review=not ok,
                metadata={
                    "action_kind": task.action_kind,
                    "ok": ok,
                    "raw_phrase": task.raw_phrase[:80],
                },
            )
        except Exception as exc:
            log.debug("Owner-Autonomie development-log: %s", exc)

        updated[task.task_id] = ts
        state = _record_task_outcome(state, task.task_id, ok=ok, ts=ts)
        summary = (result or "").replace("\n", " ")[:160]
        note = f"[Owner-Autonomie] {task.task_id}: {'OK' if ok else 'FAIL'} — {summary}"
        if on_note:
            on_note(note)
        AuditLog.action(
            "OwnerAutonomy",
            task.task_id,
            f"ok={ok} kind={task.action_kind} phrase={task.raw_phrase[:80]}",
            erfolg=bool(ok),
        )
        log.info("Owner-Autonomie ausgeführt: %s ok=%s", task.task_id, ok)
        executed += 1

    if executed:
        try:
            save_autonomy_state(state)
        except Exception as exc:
            log.debug("Owner-Autonomie-State speichern: %s", exc)

    return updated