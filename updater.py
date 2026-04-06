"""
Isaac – Dashboard Updater
=========================
Patch- und Update-Workflow für lokale ZIP-Pakete aus dem Download-Ordner.
"""

from __future__ import annotations

import asyncio
import compileall
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional

from audit import AuditLog

log = logging.getLogger("Isaac.Updater")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TARGET = BASE_DIR
BACKUP_DIR = Path.home() / "Isaac" / "backups"
STATE_PATH = BASE_DIR / "data" / "updater_state.json"
DOWNLOAD_CANDIDATES = [
    Path("/storage/emulated/0/Download"),
    Path.home() / "storage" / "downloads",
    Path("/sdcard/Download"),
]


def _ensure_state_parent():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    _ensure_state_parent()
    if not STATE_PATH.exists():
        return {"last_apply": None, "last_backup": None, "history": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"last_apply": None, "last_backup": None, "history": []}


def _save_state(state: dict):
    _ensure_state_parent()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_history(event: dict):
    state = _load_state()
    hist = list(state.get("history") or [])
    hist.append(event)
    state["history"] = hist[-50:]
    if event.get("backup_path"):
        state["last_backup"] = event["backup_path"]
    if event.get("package"):
        state["last_apply"] = {
            "package": event.get("package"),
            "ts": event.get("ts"),
            "backup_path": event.get("backup_path"),
            "ok": event.get("ok", False),
        }
    _save_state(state)


def find_download_dir() -> Optional[Path]:
    for p in DOWNLOAD_CANDIDATES:
        try:
            if p.exists() and p.is_dir():
                return p
        except Exception:
            continue
    return None


def list_packages() -> list[dict]:
    dl = find_download_dir()
    if not dl:
        return []
    items = []
    for p in sorted(dl.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        items.append({
            "name": p.name,
            "path": str(p),
            "size_bytes": st.st_size,
            "size_mb": round(st.st_size / (1024 * 1024), 2),
            "modified_ts": int(st.st_mtime),
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
        })
    return items


def _choose_package_root(names: list[str]) -> str:
    parts = [n.strip('/') for n in names if n.strip('/')]
    if not parts:
        return ""
    top_levels = {p.split('/', 1)[0] for p in parts}
    if "isaac" in top_levels:
        return "isaac"
    indicators = ("isaac_core.py", "start_isaac.sh", "monitor_server.py", "dashboard.html")
    for ind in indicators:
        if ind in parts:
            return ""
    # if there's only one top level folder, use it
    if len(top_levels) == 1:
        return next(iter(top_levels))
    return ""


def inspect_package(package_name: str) -> dict:
    pkg = _resolve_package(package_name)
    with zipfile.ZipFile(pkg) as zf:
        names = [n for n in zf.namelist() if not n.endswith('/')]
        root = _choose_package_root(names)
        display_names = [n[len(root)+1:] if root and n.startswith(root + '/') else n for n in names]
        py_files = [n for n in display_names if n.endswith('.py')]
        notes = [n for n in display_names if n.lower().endswith(('.txt', '.md', '.json')) and ('manifest' in n.lower() or 'notes' in n.lower() or 'readme' in n.lower())]
        key_files = [n for n in display_names if Path(n).name in {'isaac_core.py','monitor_server.py','dashboard.html','executor.py','updater.py'}]
        return {
            "ok": True,
            "package": pkg.name,
            "path": str(pkg),
            "root_mode": root or ".",
            "file_count": len(names),
            "python_files": len(py_files),
            "key_files": sorted(key_files),
            "notes": sorted(notes)[:20],
            "sample_files": sorted(display_names)[:60],
        }


def _resolve_package(package_name: str) -> Path:
    dl = find_download_dir()
    if not dl:
        raise FileNotFoundError("Kein Download-Ordner gefunden")
    pkg = dl / package_name
    if not pkg.exists():
        raise FileNotFoundError(f"Paket nicht gefunden: {package_name}")
    return pkg


def _copy_contents(src: Path, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            if target.exists() and target.is_file():
                target.unlink()
            _copy_contents(item, target)
        else:
            if target.exists() and target.is_dir():
                shutil.rmtree(target)
            shutil.copy2(item, target)


def _cleanup_bytecode(target_dir: Path):
    for p in target_dir.rglob('__pycache__'):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    for p in target_dir.rglob('*.pyc'):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def _make_backup(target_dir: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    backup = BACKUP_DIR / f'isaac_backup_{stamp}'
    shutil.copytree(target_dir, backup)
    return backup


def apply_package(package_name: str, target_dir: Optional[str] = None, create_backup: bool = True) -> dict:
    pkg = _resolve_package(package_name)
    target = Path(target_dir).expanduser() if target_dir else DEFAULT_TARGET
    target = target.resolve()
    if not target.exists():
        raise FileNotFoundError(f'Zielordner nicht gefunden: {target}')

    backup_path = None
    stamp = time.strftime('%Y-%m-%d %H:%M:%S')
    with tempfile.TemporaryDirectory(prefix='isaac_updater_') as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(pkg) as zf:
            zf.extractall(tmp_path)
            names = [n for n in zf.namelist() if not n.endswith('/')]
        root = _choose_package_root(names)
        src = tmp_path / root if root else tmp_path
        if not src.exists():
            raise FileNotFoundError(f'Paketwurzel nicht gefunden: {src}')
        if create_backup:
            backup_path = _make_backup(target)
        _copy_contents(src, target)
        _cleanup_bytecode(target)
        compiled = compileall.compile_dir(str(target), quiet=1, force=False)
        result = {
            'ok': bool(compiled),
            'package': pkg.name,
            'target_dir': str(target),
            'backup_path': str(backup_path) if backup_path else None,
            'compiled': bool(compiled),
            'root_mode': root or '.',
            'ts': stamp,
        }
        _record_history(result)
        AuditLog.action('Updater', 'apply_package', f"{pkg.name} -> {target}", erfolg=bool(compiled))
        return result


def rollback_last_backup(target_dir: Optional[str] = None, backup_path: Optional[str] = None) -> dict:
    state = _load_state()
    backup = Path(backup_path) if backup_path else Path(state.get('last_backup') or '')
    if not backup or not backup.exists():
        raise FileNotFoundError('Kein Backup für Rollback gefunden')
    target = Path(target_dir).expanduser() if target_dir else DEFAULT_TARGET
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(backup, target)
    _cleanup_bytecode(target)
    compiled = compileall.compile_dir(str(target), quiet=1, force=False)
    result = {
        'ok': bool(compiled),
        'rollback_from': str(backup),
        'target_dir': str(target),
        'compiled': bool(compiled),
        'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    _record_history({'package': 'ROLLBACK', 'backup_path': str(backup), 'ok': bool(compiled), 'ts': result['ts']})
    AuditLog.action('Updater', 'rollback', str(backup), erfolg=bool(compiled))
    return result


def status() -> dict:
    state = _load_state()
    return {
        'ok': True,
        'download_dir': str(find_download_dir()) if find_download_dir() else None,
        'packages': list_packages(),
        'last_apply': state.get('last_apply'),
        'last_backup': state.get('last_backup'),
        'history': state.get('history')[-10:],
    }


async def schedule_process_restart(delay: float = 1.5, script_name: str = 'isaac_core.py'):
    await asyncio.sleep(delay)
    script = BASE_DIR / script_name
    os.execv(sys.executable, [sys.executable, str(script)])
