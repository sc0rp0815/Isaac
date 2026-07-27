"""Isaac – Chrome Tab Reader (Android, Magisk root via Termux bridge).

Lists URLs from Chrome's on-device tab storage. Owner/admin only.
Does NOT read cookies or passwords — only tab URL strings.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from audit import AuditLog
from config import is_owner_equivalent_mode

log = logging.getLogger("Isaac.ChromeTabs")

CHROME_TABS_DIR = "/data/data/com.android.chrome/app_tabs/0"
CHROME_CUSTOM_TABS_DIR = "/data/data/com.android.chrome/app_tabs/custom_tabs"
CHROME_SESSIONS_DIR = "/data/data/com.android.chrome/app_chrome/Default/Sessions"

_URL_RE = re.compile(r"https?://[^\x00-\x1f\s\"'<>\\]{6,300}", re.I)

_NOISE_HOST_SUBSTR = (
    "connectivitycheck.gstatic.com",
    "clients.google.com",
    "clients1.google.com",
    "clients2.google.com",
    "clients3.google.com",
    "clients4.google.com",
    "clients6.google.com",
    "android.clients.google.com",
    "safebrowsing.google.com",
    "update.googleapis.com",
    "fonts.gstatic.com",
    "fonts.googleapis.com",
    "gstatic.com/generate_204",
    "app-measurement.com",
    "doubleclick.net",
    "googleads.",
    "pagead",
    "3p-payments.googleusercontent.com",
)

# Session cache for "öffne tab N"
_last_list: list[dict[str, Any]] = []
_last_list_at: float = 0.0


def _owner_ok() -> Optional[str]:
    if is_owner_equivalent_mode():
        return None
    return "Chrome-Tabs nur im Admin-Modus."


async def _root_sh(cmd: str, *, timeout: float = 45.0) -> dict[str, Any]:
    """Run command as Magisk su through Termux bridge."""
    from termux_bridge import bridge_available, run_termux_command

    if not bridge_available():
        return {"ok": False, "error": "Termux-Brücke nicht verfügbar", "stdout": ""}
    # Escape for su -c '...'
    escaped = cmd.replace("'", "'\\''")
    full = f"export PATH=/system/bin:/system/xbin:$PATH; su -c '{escaped}'"
    return await run_termux_command(["sh", "-c", full], timeout=timeout)


def redact_url(url: str) -> str:
    """Strip sensitive query params for display/logs."""
    try:
        p = urlparse(url)
        if not p.query:
            return url[:220]
        q = parse_qs(p.query, keep_blank_values=True)
        drop = {
            "token",
            "access_token",
            "refresh_token",
            "id_token",
            "code",
            "password",
            "passwd",
            "client_secret",
            "state",
            "code_challenge",
            "nonce",
            "authuser",
            "session_state",
            "uaid",
        }
        cleaned = {k: v for k, v in q.items() if k.lower() not in drop}
        # long oauth noise → host + path only
        if any(x in (p.netloc or "").lower() for x in ("accounts.google.com", "login.live.com", "oauth")):
            if len(p.query) > 40:
                return f"{p.scheme}://{p.netloc}{p.path}"[:220]
        new_q = urlencode({k: v[0] if len(v) == 1 else v for k, v in cleaned.items()}, doseq=True)
        return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, ""))[:220]
    except Exception:
        return (url or "")[:220]


def is_noise_url(url: str) -> bool:
    u = (url or "").lower()
    if not u.startswith("http"):
        return True
    if any(n in u for n in _NOISE_HOST_SUBSTR):
        return True
    if "generate_204" in u:
        return True
    # chrome internal
    if u.startswith("chrome://") or u.startswith("chrome-native://"):
        return True
    # tiny asset hosts often not useful tabs
    if ".assets.github.dev" in u and "/assets/" in u:
        return True
    return False


def extract_urls_from_text(text: str) -> list[str]:
    found: list[str] = []
    for m in _URL_RE.finditer(text or ""):
        raw = m.group(0).rstrip(").,;]")
        # trim trailing garbage from binary strings
        raw = re.sub(r"[\x00-\x1f]+$", "", raw)
        if len(raw) < 10:
            continue
        found.append(raw)
    return found


def filter_and_dedupe(urls: list[str], *, full: bool = False) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if not full and is_noise_url(u):
            continue
        # normalize key: scheme+host+path without fragment
        try:
            p = urlparse(u)
            key = f"{p.scheme}://{p.netloc}{p.path}".rstrip("/").lower()
        except Exception:
            key = u.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


async def status() -> dict[str, Any]:
    blocked = _owner_ok()
    if blocked:
        return {"ok": False, "error": blocked}
    from termux_bridge import bridge_available

    st: dict[str, Any] = {
        "ok": True,
        "bridge": bridge_available(),
        "magisk_su": False,
        "chrome_tabs_dir": False,
        "tab_files": 0,
    }
    if not st["bridge"]:
        st["ok"] = False
        st["error"] = "Termux-Brücke down"
        return st
    r = await _root_sh("id; ls /data/data/com.android.chrome/app_tabs/0 2>&1 | wc -l")
    out = (r.get("stdout") or "") + (r.get("stderr") or "")
    st["magisk_su"] = "uid=0" in out and "magisk" in out.lower() or (
        r.get("ok") and "uid=0" in out
    )
    if "app_tabs" in out or re.search(r"\b\d+\b", out.splitlines()[-1] if out.strip() else ""):
        st["chrome_tabs_dir"] = True
    m = re.search(r"(\d+)\s*$", out.strip())
    if m:
        st["tab_files"] = int(m.group(1))
    if not st["magisk_su"] and not r.get("ok"):
        st["ok"] = False
        st["error"] = (r.get("error") or out or "su failed")[:200]
    return st


async def list_tabs(
    *,
    limit: int = 40,
    full: bool = False,
    max_files: int = 80,
) -> dict[str, Any]:
    """Return recent Chrome tab URLs from device storage."""
    blocked = _owner_ok()
    if blocked:
        return {"ok": False, "error": blocked, "tabs": []}

    from termux_bridge import bridge_available

    if not bridge_available():
        return {
            "ok": False,
            "error": "Termux-Brücke nicht verfügbar — apps status",
            "tabs": [],
        }

    # Newest tab state files first
    dirs = [CHROME_TABS_DIR]
    if full:
        dirs.append(CHROME_CUSTOM_TABS_DIR)

    dir_list = " ".join(f"'{d}'" for d in dirs)
    # Collect up to max_files recent files + session files
    cmd = (
        f"find {dir_list} -type f 2>/dev/null "
        f"| head -n 500 "
        f"| xargs -r ls -1t 2>/dev/null "
        f"| head -n {int(max_files)}; "
        f"ls -1t {CHROME_SESSIONS_DIR}/Tabs_* 2>/dev/null | head -n 4"
    )
    listing = await _root_sh(cmd, timeout=30.0)
    files_raw = (listing.get("stdout") or "").strip().splitlines()
    files = [f.strip() for f in files_raw if f.strip().startswith("/")]
    if not files:
        err = listing.get("error") or listing.get("stderr") or "keine Tab-Dateien"
        # probe su
        probe = await _root_sh("id")
        if "uid=0" not in (probe.get("stdout") or ""):
            return {
                "ok": False,
                "error": f"Magisk su nicht nutzbar: {probe.get('stdout') or probe.get('error')}",
                "tabs": [],
            }
        return {"ok": False, "error": str(err)[:200], "tabs": []}

    # strings from those files in one su call (bounded)
    # quote each path
    quoted = " ".join(f"'{p}'" for p in files[:max_files])
    extract_cmd = (
        f"for f in {quoted}; do "
        f"[ -f \"$f\" ] && strings \"$f\" 2>/dev/null; "
        f"done"
    )
    extracted = await _root_sh(extract_cmd, timeout=60.0)
    blob = extracted.get("stdout") or ""
    if not blob and not extracted.get("ok"):
        return {
            "ok": False,
            "error": (extracted.get("error") or "strings failed")[:200],
            "tabs": [],
        }

    raw_urls = extract_urls_from_text(blob)
    urls = filter_and_dedupe(raw_urls, full=full)[: max(1, int(limit))]

    tabs = [
        {
            "index": i + 1,
            "url": u,
            "display": redact_url(u),
            "host": (urlparse(u).netloc or "")[:80],
        }
        for i, u in enumerate(urls)
    ]

    global _last_list, _last_list_at
    _last_list = tabs
    _last_list_at = time.time()

    AuditLog.action(
        "ChromeTabs",
        "list",
        f"n={len(tabs)} files={len(files)} full={full}",
        erfolg=True,
    )
    return {
        "ok": True,
        "tabs": tabs,
        "count": len(tabs),
        "files_scanned": len(files),
        "full": full,
    }


def get_cached_tab(index: int) -> Optional[dict[str, Any]]:
    if not _last_list:
        return None
    if index < 1 or index > len(_last_list):
        return None
    return _last_list[index - 1]


def format_tabs_report(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"[Chrome Tabs] {result.get('error', 'Fehler')}"
    tabs = result.get("tabs") or []
    if not tabs:
        return (
            "[Chrome Tabs] Keine nutzbaren URLs gefunden "
            f"(files_scanned={result.get('files_scanned', 0)})."
        )
    lines = [
        f"[Chrome Tabs] {len(tabs)} URLs "
        f"(files={result.get('files_scanned', 0)}, "
        f"{'full' if result.get('full') else 'gefiltert'})",
        "",
    ]
    for t in tabs:
        lines.append(f"  {t['index']:2}. {t.get('display') or t.get('url')}")
    lines.append("")
    lines.append("Öffnen: öffne tab 3")
    return "\n".join(lines)
