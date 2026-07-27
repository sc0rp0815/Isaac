"""Isaac – Chrome/Device secrets reader (Android, Magisk root via Termux).

Owner/admin only. Pulls what is readable on-device:
- Cookie catalog (host/name/meta; values are Chrome v10-encrypted)
- Autofill form history (often plaintext)
- Addresses / masked cards / IBANs
- Android accounts (dumpsys)
- Google Password Manager local DB status (hashes only, no cleartext)

Does NOT claim to break Android Keystore. Cookie *values* need OSCrypt key
from the Chrome process / Keystore — documented in results.
"""

from __future__ import annotations

import base64
import logging
import re
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from audit import AuditLog
from config import DATA_DIR, is_owner_equivalent_mode

log = logging.getLogger("Isaac.ChromeSecrets")

CHROME_DEFAULT = "/data/data/com.android.chrome/app_chrome/Default"
CHROME_COOKIES = f"{CHROME_DEFAULT}/Cookies"
CHROME_WEB_DATA = f"{CHROME_DEFAULT}/Web Data"
CHROME_ACCOUNT_WEB = f"{CHROME_DEFAULT}/Account Web Data"
CHROME_LOCAL_STATE = "/data/data/com.android.chrome/app_chrome/Local State"
GMS_PASSWORD_DB = "/data/data/com.google.android.gms/databases/password_manager.db"

_DUMP_DIR = Path(DATA_DIR) / "chrome_secrets_dump"
_CACHE: dict[str, Any] = {"at": 0.0, "data": {}}


def _owner_ok() -> Optional[str]:
    if is_owner_equivalent_mode():
        return None
    return "Chrome-Secrets nur im Admin-Modus."


async def _root_sh(cmd: str, *, timeout: float = 60.0) -> dict[str, Any]:
    from chrome_tabs import _root_sh as root_sh

    return await root_sh(cmd, timeout=timeout)


async def _pull_file(remote: str, *, max_bytes: int = 12_000_000) -> tuple[Optional[bytes], str]:
    """Pull a root-only file via base64 over Magisk su."""
    r = await _root_sh(
        f'if [ -f "{remote}" ]; then wc -c < "{remote}"; base64 "{remote}"; else echo MISSING; fi',
        timeout=120.0,
    )
    out = r.get("stdout") or ""
    if "MISSING" in out[:40] or not out.strip():
        return None, (r.get("error") or "Datei fehlt")[:200]
    lines = out.splitlines()
    # first line may be size
    body = out
    if lines and lines[0].strip().isdigit():
        body = "\n".join(lines[1:])
    data = "".join(body.split())
    try:
        raw = base64.b64decode(data, validate=False)
    except Exception as exc:
        return None, f"base64 decode: {exc}"
    if len(raw) > max_bytes:
        return None, f"Datei zu groß ({len(raw)} B)"
    if len(raw) < 16:
        return None, f"zu klein / leer ({len(raw)} B)"
    return raw, ""


# path tracking for temp sqlite files (Connection has no __dict__ on some builds)
_SQLITE_TMP: dict[int, str] = {}


def _open_sqlite(raw: bytes) -> sqlite3.Connection:
    tmp = tempfile.NamedTemporaryFile(prefix="isaac_chrome_", suffix=".db", delete=False)
    tmp.write(raw)
    tmp.flush()
    tmp.close()
    con = sqlite3.connect(f"file:{tmp.name}?mode=ro", uri=True)
    _SQLITE_TMP[id(con)] = tmp.name
    return con


def _close_sqlite(con: sqlite3.Connection) -> None:
    path = _SQLITE_TMP.pop(id(con), None)
    try:
        con.close()
    except Exception:
        pass
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def _safe_rows(con: sqlite3.Connection, sql: str, params: tuple = (), limit: int = 200) -> list[tuple]:
    try:
        cur = con.cursor()
        cur.execute(sql, params)
        return cur.fetchmany(limit)
    except Exception as exc:
        log.debug("sqlite query failed: %s", exc)
        return []


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    rows = _safe_rows(
        con,
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    )
    return bool(rows)


def parse_cookies_db(raw: bytes, *, host_filter: str = "", limit: int = 80) -> dict[str, Any]:
    con = _open_sqlite(raw)
    try:
        total = 0
        rows = _safe_rows(
            con,
            "SELECT count(*) FROM cookies",
        )
        if rows:
            total = int(rows[0][0] or 0)
        q = (
            "SELECT host_key, name, path, is_secure, is_httponly, "
            "length(encrypted_value), length(value), "
            "CASE WHEN value IS NOT NULL AND value != '' THEN 1 ELSE 0 END "
            "FROM cookies"
        )
        params: tuple = ()
        if host_filter:
            q += " WHERE host_key LIKE ?"
            params = (f"%{host_filter}%",)
        q += " ORDER BY last_access_utc DESC LIMIT ?"
        params = params + (int(limit),)
        items = []
        plaintext = 0
        encrypted = 0
        for host, name, path, secure, http_only, elen, vlen, has_plain in _safe_rows(
            con, q, params, limit=limit
        ):
            if has_plain:
                plaintext += 1
            else:
                encrypted += 1
            items.append(
                {
                    "host": host or "",
                    "name": name or "",
                    "path": path or "/",
                    "secure": bool(secure),
                    "http_only": bool(http_only),
                    "encrypted_bytes": int(elen or 0),
                    "has_plaintext": bool(has_plain),
                    "value_note": "plaintext" if has_plain else "v10-encrypted",
                }
            )
        # host summary
        hosts: dict[str, int] = {}
        for host, cnt in _safe_rows(
            con,
            "SELECT host_key, count(*) FROM cookies GROUP BY host_key ORDER BY count(*) DESC LIMIT 40",
        ):
            hosts[str(host)] = int(cnt)
        return {
            "ok": True,
            "total": total,
            "returned": len(items),
            "plaintext_in_page": plaintext,
            "encrypted_in_page": encrypted,
            "cookies": items,
            "top_hosts": hosts,
            "decrypt_status": (
                "Cookie-Werte sind Chrome v10-verschlüsselt (Android Keystore/OSCrypt). "
                "Klartext-Values aktuell 0 — Entschlüsselung braucht den Prozess-Key "
                "(nicht in Local State als DPAPI-Key vorhanden)."
            ),
        }
    finally:
        _close_sqlite(con)


def parse_web_data(raw: bytes, *, limit: int = 60) -> dict[str, Any]:
    con = _open_sqlite(raw)
    try:
        autofill = []
        for name, value, count in _safe_rows(
            con,
            "SELECT name, value, count FROM autofill "
            "WHERE value IS NOT NULL AND value != '' "
            "ORDER BY count DESC, date_last_used DESC LIMIT ?",
            (int(limit),),
            limit=limit,
        ):
            autofill.append(
                {
                    "field": str(name or "")[:80],
                    "value": str(value or "")[:200],
                    "count": int(count or 0),
                }
            )
        addresses = []
        if _table_exists(con, "address_type_tokens"):
            by_guid: dict[str, dict[str, str]] = {}
            for guid, typ, value in _safe_rows(
                con,
                "SELECT guid, type, value FROM address_type_tokens "
                "WHERE value IS NOT NULL AND value != '' LIMIT 500",
                limit=500,
            ):
                g = str(guid)
                by_guid.setdefault(g, {})
                # Chromium field types (subset)
                label = {
                    3: "first_name",
                    5: "last_name",
                    7: "full_name",
                    9: "email",
                    14: "phone",
                    33: "city",
                    35: "zip",
                    36: "country",
                    77: "street_full",
                    103: "street",
                    104: "house",
                }.get(int(typ), f"t{typ}")
                if value and label not in by_guid[g]:
                    by_guid[g][label] = str(value)[:120]
            for g, fields in list(by_guid.items())[:20]:
                addresses.append({"guid": g[:12], **fields})
        return {
            "ok": True,
            "autofill": autofill,
            "autofill_count": len(autofill),
            "addresses": addresses,
        }
    finally:
        _close_sqlite(con)


def parse_account_web_data(raw: bytes) -> dict[str, Any]:
    con = _open_sqlite(raw)
    try:
        cards = []
        if _table_exists(con, "masked_credit_cards"):
            for row in _safe_rows(
                con,
                "SELECT name_on_card, network, last_four, exp_month, exp_year, "
                "bank_name, nickname, product_description "
                "FROM masked_credit_cards LIMIT 40",
                limit=40,
            ):
                cards.append(
                    {
                        "name": row[0] or "",
                        "network": row[1] or "",
                        "last_four": row[2] or "",
                        "exp": f"{row[3]}/{row[4]}",
                        "bank": row[5] or "",
                        "nickname": row[6] or "",
                        "product": (row[7] or "")[:80],
                    }
                )
        ibans = []
        if _table_exists(con, "masked_ibans"):
            for row in _safe_rows(
                con,
                "SELECT prefix, suffix, nickname FROM masked_ibans LIMIT 20",
                limit=20,
            ):
                ibans.append(
                    {
                        "masked": f"{row[0]}****{row[1]}",
                        "nickname": row[2] or "",
                    }
                )
        return {"ok": True, "cards": cards, "ibans": ibans}
    finally:
        _close_sqlite(con)


async def list_android_accounts() -> dict[str, Any]:
    r = await _root_sh("dumpsys account 2>/dev/null | head -n 80", timeout=30.0)
    out = r.get("stdout") or ""
    accounts = []
    for m in re.finditer(
        r"Account \{name=([^,]+), type=([^}]+)\}",
        out,
    ):
        accounts.append({"name": m.group(1).strip(), "type": m.group(2).strip()})
    return {"ok": bool(accounts) or r.get("ok"), "accounts": accounts, "raw_preview": out[:400]}


async def password_manager_status() -> dict[str, Any]:
    """GMS password_manager.db — typically hashes only, no cleartext passwords."""
    login_data = await _root_sh(
        f'ls -la "{CHROME_DEFAULT}/Login Data" 2>&1; '
        f'ls -la "{GMS_PASSWORD_DB}" 2>&1',
        timeout=20.0,
    )
    listing = login_data.get("stdout") or ""
    has_login_data = "Login Data" in listing and "No such" not in listing
    raw, err = await _pull_file(GMS_PASSWORD_DB, max_bytes=2_000_000)
    info: dict[str, Any] = {
        "ok": True,
        "chrome_login_data_present": has_login_data,
        "gms_db": bool(raw),
        "note": (
            "Chrome Android speichert hier keine Klartext-Login-Data-Datei. "
            "Passwörter liegen in Google Password Manager (Cloud + Keystore). "
            "Lokal oft nur Leak-Check-Hashes."
        ),
    }
    if not raw:
        info["gms_error"] = err
        return info
    con = _open_sqlite(raw)
    try:
        tables = [
            r[0]
            for r in _safe_rows(
                con, "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
        info["tables"] = tables
        if "leak_check_reencryption" in tables:
            n = _safe_rows(con, "SELECT count(*) FROM leak_check_reencryption")
            info["leak_check_entries"] = int(n[0][0]) if n else 0
            accs = [
                r[0]
                for r in _safe_rows(
                    con,
                    "SELECT DISTINCT accountName FROM leak_check_reencryption LIMIT 20",
                )
            ]
            info["accounts_with_hashes"] = accs
        if "device_settings_table" in tables:
            for name, val in _safe_rows(
                con, "SELECT settingName, value FROM device_settings_table LIMIT 20"
            ):
                if isinstance(val, (bytes, memoryview)):
                    val = bytes(val).decode("utf-8", errors="replace")
                info.setdefault("settings", {})[str(name)] = str(val)[:80]
    finally:
        _close_sqlite(con)
    return info


# Live-decrypt cache (plaintext values — never written to audit detail)
_LIVE_CACHE: dict[str, Any] = {"at": 0.0, "items": []}

_GOOGLE_COOKIE_NAMES = {
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "NID",
    "SIDCC",
    "OSID",
    "__Secure-1PSID",
    "__Secure-3PSID",
    "__Secure-1PSIDTS",
    "__Secure-3PSIDTS",
    "__Secure-1PSIDCC",
    "__Secure-3PSIDCC",
    "__Secure-OSID",
    "__Secure-BUCKET",
}


def _guess_host_for_name(name: str) -> str:
    n = name or ""
    if n in _GOOGLE_COOKIE_NAMES or (n.startswith("__Secure-") and "PSID" in n):
        return ".google.com"
    if n in {"c_user", "xs", "datr", "sb", "fr"}:
        return ".facebook.com"
    if n in {"auth_token", "ct0", "twid", "kdt"}:
        return ".x.com"
    if n in {"li_at"}:
        return ".linkedin.com"
    if "next-auth" in n.lower():
        return "(next-auth)"
    if n.lower() in {"sessionid", "session", "connect.sid", "user_session"}:
        return "(session)"
    if n.lower() in {"access_token", "refresh_token", "id_token", "Bearer", "token", "jwt"}:
        return "(oauth-token)"
    if n.lower() in {"password", "passwd"}:
        return "(password-field)"
    return "(unknown)"


def _mask_value(value: str, *, reveal: bool) -> str:
    if reveal:
        return value
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}…{value[-4:]} ({len(value)}c)"


async def _ensure_memscan_on_device() -> str:
    """Copy memscan script to /sdcard and return device path."""
    src = Path(__file__).resolve().parent / "scripts" / "android_chrome_memscan.py"
    dest = "/sdcard/Download/isaac_chrome_memscan.py"
    if not src.exists():
        return ""
    try:
        Path("/sdcard/Download").mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(src.read_bytes())
    except OSError:
        b64 = base64.b64encode(src.read_bytes()).decode()
        # small script only
        await _root_sh(
            f"echo {b64} | base64 -d > {dest} 2>/dev/null; chmod 644 {dest}",
            timeout=30.0,
        )
    return dest


async def live_decrypt_sessions(
    *,
    reveal: bool = True,
    limit: int = 80,
    name_filter: str = "",
) -> dict[str, Any]:
    """Extract plaintext cookie/token values from live Chrome process memory.

    Bypasses OSCrypt by reading values already decrypted in Chrome's address
    space. Requires Magisk root + Chrome running.
    """
    blocked = _owner_ok()
    if blocked:
        return {"ok": False, "error": blocked, "items": []}

    from termux_bridge import bridge_available

    if not bridge_available():
        return {"ok": False, "error": "Termux-Brücke nicht verfügbar", "items": []}

    script = await _ensure_memscan_on_device()
    if not script:
        return {"ok": False, "error": "memscan script fehlt", "items": []}

    pid_probe = await _root_sh("pidof com.android.chrome 2>/dev/null", timeout=15.0)
    if not (pid_probe.get("stdout") or "").strip():
        await _root_sh(
            "am start -n com.android.chrome/com.google.android.apps.chrome.Main "
            ">/dev/null 2>&1; sleep 2; pidof com.android.chrome",
            timeout=20.0,
        )

    cmd = (
        "export PATH=/data/data/com.termux/files/usr/bin:/system/bin:$PATH; "
        f"python3 {script} 2>/dev/null"
    )
    r = await _root_sh(cmd, timeout=120.0)
    out = r.get("stdout") or ""
    if "FOUND=" not in out and "PID=" not in out:
        return {
            "ok": False,
            "error": (r.get("error") or out or "memscan fehlgeschlagen")[:300],
            "items": [],
        }

    meta: dict[str, Any] = {"method": "process_memory", "pid": None, "regions": 0}
    items: list[dict[str, Any]] = []
    nf = (name_filter or "").lower().strip()

    for line in out.splitlines():
        if line.startswith("PID="):
            try:
                meta["pid"] = int(line.split("=", 1)[1])
            except ValueError:
                pass
            continue
        if line.startswith("SCANNED_REGIONS="):
            try:
                meta["regions"] = int(line.split("=", 1)[1])
            except ValueError:
                pass
            continue
        if line.startswith("FOUND=") or line.startswith("MAPS="):
            continue
        if "|" not in line:
            continue
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        source, name, value = parts[0], parts[1], parts[2]
        if nf and nf not in name.lower() and nf not in value.lower():
            continue
        # drop Set-Cookie attribute noise
        if name.lower() in {
            "expires",
            "domain",
            "path",
            "max-age",
            "samesite",
            "secure",
            "httponly",
            "ma",
            "priority",
        }:
            continue
        if value.lower() in {"function", "true", "false", "none", "null", "undefined"}:
            continue
        if value.startswith("function"):
            continue
        host = _guess_host_for_name(name)
        items.append(
            {
                "source": source,
                "host": host,
                "name": name,
                "value": value if reveal else _mask_value(value, reveal=False),
                "value_len": len(value),
                "reveal": reveal,
            }
        )

    best: dict[str, dict[str, Any]] = {}
    for it in items:
        k = f"{it['name']}|{it['host']}|{it['value'][:24]}"
        prev = best.get(k)
        if not prev or it["value_len"] > prev["value_len"]:
            best[k] = it
    # collapse further by name+host keep longest
    by_nh: dict[str, dict[str, Any]] = {}
    for it in best.values():
        k = f"{it['name']}|{it['host']}"
        prev = by_nh.get(k)
        if not prev or it["value_len"] > prev["value_len"]:
            by_nh[k] = it
    items = sorted(by_nh.values(), key=lambda x: (-x["value_len"], x["name"]))[:limit]

    _LIVE_CACHE["at"] = time.time()
    if reveal:
        _LIVE_CACHE["items"] = items

    try:
        import json

        _DUMP_DIR.mkdir(parents=True, exist_ok=True)
        export = {
            "at": _LIVE_CACHE["at"],
            "method": "process_memory",
            "count": len(items),
            "items": [
                {
                    "host": i["host"],
                    "name": i["name"],
                    "value": i["value"],
                    "value_len": i["value_len"],
                }
                for i in items
            ],
        }
        (_DUMP_DIR / "live_sessions.json").write_text(
            json.dumps(export, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        log.debug("live export skip: %s", exc)

    AuditLog.action(
        "ChromeSecrets",
        "live_decrypt",
        f"n={len(items)} pid={meta.get('pid')} regions={meta.get('regions')} reveal={reveal}",
        erfolg=True,
    )
    return {
        "ok": True,
        "items": items,
        "count": len(items),
        "meta": meta,
        "note": (
            "Klartext aus Chrome-Prozessspeicher (OSCrypt umgangen via live memory). "
            "Chrome muss laufen. Keine kryptografische DB-Entschlüsselung."
        ),
    }


def format_live_decrypt_report(result: dict[str, Any], *, reveal: bool = True) -> str:
    if not result.get("ok"):
        return f"[Chrome Decrypt] {result.get('error', 'Fehler')}"
    items = result.get("items") or []
    meta = result.get("meta") or {}
    lines = [
        f"[Chrome Decrypt / Live Memory] {len(items)} Werte",
        f"PID={meta.get('pid')} regions={meta.get('regions')} method={meta.get('method')}",
        result.get("note") or "",
        "",
    ]
    by_host: dict[str, list] = {}
    for it in items:
        by_host.setdefault(it.get("host") or "?", []).append(it)
    for host, rows in sorted(by_host.items(), key=lambda x: (-len(x[1]), x[0])):
        lines.append(f"## {host} ({len(rows)})")
        for it in rows[:40]:
            val = str(it.get("value") or "")
            if not reveal:
                val = _mask_value(val, reveal=False)
            lines.append(f"  {it.get('name')}={val}")
        lines.append("")
    if not items:
        lines.append("(keine Werte — Chrome öffnen, Seiten laden, dann erneut)")
    lines.append(f"Export: {_DUMP_DIR / 'live_sessions.json'}")
    jar = result.get("cookie_jar") or {}
    if jar.get("ok"):
        lines.append(f"Cookie-Jar: {jar.get('netscape_path')} ({jar.get('count')} cookies)")
        lines.append(f"Cookie-JSON: {jar.get('json_path')}")
    return "\n".join(lines).rstrip()


def _normalize_cookie_domain(host: str, name: str) -> str:
    h = (host or "").strip()
    if not h or h.startswith("("):
        # fallback guesses
        guessed = _guess_host_for_name(name)
        if guessed.startswith("("):
            return ""
        h = guessed
    if h and not h.startswith(".") and h.count(".") >= 1:
        # leading dot for domain cookies
        if name in _GOOGLE_COOKIE_NAMES or name.startswith("__Secure-"):
            if not h.startswith("."):
                h = "." + h.lstrip(".")
    return h


def items_to_cookie_jar(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert live-decrypt items into cookie-jar entries (skip non-cookie tokens)."""
    skip_names = {
        "Bearer",
        "access_token",
        "refresh_token",
        "id_token",
        "jwt",
        "token",
        "password",
        "passwd",
        "Passwd",
    }
    skip_hosts = {"(oauth-token)", "(password-field)"}
    jar: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in items or []:
        name = str(it.get("name") or "")
        value = str(it.get("value") or "")
        if not name or not value:
            continue
        if name in skip_names:
            continue
        host = str(it.get("host") or "")
        if host in skip_hosts:
            continue
        domain = _normalize_cookie_domain(host, name)
        if not domain or domain.startswith("("):
            continue
        # cookie value safety
        if any(c in value for c in " \t\r\n;"):
            continue
        key = f"{domain}|{name}|{value[:32]}"
        if key in seen:
            continue
        seen.add(key)
        jar.append(
            {
                "domain": domain,
                "include_subdomains": domain.startswith("."),
                "path": "/",
                "secure": name.startswith("__Secure-")
                or name.startswith("__Host-")
                or "PSID" in name
                or domain.endswith("google.com"),
                "expires": 0,  # session
                "name": name,
                "value": value,
            }
        )
    return jar


def write_cookie_jar(
    entries: list[dict[str, Any]],
    *,
    basename: str = "cookies",
) -> dict[str, Any]:
    """Write Netscape cookies.txt + JSON jar. Owner dump dir."""
    import json

    blocked = _owner_ok()
    if blocked:
        return {"ok": False, "error": blocked}
    _DUMP_DIR.mkdir(parents=True, exist_ok=True)
    netscape_path = _DUMP_DIR / f"{basename}.txt"
    json_path = _DUMP_DIR / f"{basename}.json"
    lines = [
        "# Netscape HTTP Cookie File",
        "# https://curl.se/docs/http-cookies.html",
        "# Generated by Isaac chrome_secrets (live memory decrypt)",
        "",
    ]
    for e in entries:
        domain = e.get("domain") or ""
        flag = "TRUE" if e.get("include_subdomains") else "FALSE"
        path = e.get("path") or "/"
        secure = "TRUE" if e.get("secure") else "FALSE"
        expires = int(e.get("expires") or 0)
        name = e.get("name") or ""
        value = e.get("value") or ""
        # tab-separated Netscape
        lines.append(
            f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}"
        )
    netscape_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {"count": len(entries), "cookies": entries},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # also curl header style
    header_path = _DUMP_DIR / f"{basename}.header.txt"
    by_domain: dict[str, list[str]] = {}
    for e in entries:
        d = e.get("domain") or ""
        by_domain.setdefault(d, []).append(f"{e.get('name')}={e.get('value')}")
    hdr_lines = []
    for d, pairs in sorted(by_domain.items()):
        hdr_lines.append(f"# {d}")
        hdr_lines.append("Cookie: " + "; ".join(pairs))
        hdr_lines.append("")
    header_path.write_text("\n".join(hdr_lines), encoding="utf-8")

    AuditLog.action(
        "ChromeSecrets",
        "cookie_jar_export",
        f"n={len(entries)} {netscape_path.name}",
        erfolg=True,
    )
    return {
        "ok": True,
        "count": len(entries),
        "netscape_path": str(netscape_path),
        "json_path": str(json_path),
        "header_path": str(header_path),
    }


async def export_cookie_jar(
    *,
    refresh_live: bool = True,
    reveal: bool = True,
    basename: str = "cookies",
) -> dict[str, Any]:
    """Build cookie jar from live decrypt (refresh optional)."""
    blocked = _owner_ok()
    if blocked:
        return {"ok": False, "error": blocked}
    items = _LIVE_CACHE.get("items") or []
    live_meta: dict[str, Any] = {}
    if refresh_live or not items:
        live = await live_decrypt_sessions(reveal=True, limit=120)
        if not live.get("ok"):
            return {"ok": False, "error": live.get("error") or "live decrypt failed"}
        items = live.get("items") or []
        live_meta = live.get("meta") or {}
    entries = items_to_cookie_jar(items)
    written = write_cookie_jar(entries, basename=basename)
    written["live_count"] = len(items)
    written["meta"] = live_meta
    written["skipped_tokens"] = len(items) - len(entries)
    return written


def format_cookie_jar_report(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"[Cookie Jar] {result.get('error', 'Fehler')}"
    return (
        f"[Cookie Jar] {result.get('count', 0)} Cookies exportiert\n"
        f"  Netscape: {result.get('netscape_path')}\n"
        f"  JSON:     {result.get('json_path')}\n"
        f"  Header:   {result.get('header_path')}\n"
        f"  live_items={result.get('live_count', 0)} "
        f"skipped_non_cookie={result.get('skipped_tokens', 0)}\n"
        f"  Nutzung: curl -b {result.get('netscape_path')} https://…"
    )


async def collect_secrets(
    *,
    host_filter: str = "",
    cookie_limit: int = 60,
    autofill_limit: int = 50,
    include_dump: bool = False,
    include_live: bool = False,
    reveal_live: bool = True,
) -> dict[str, Any]:
    blocked = _owner_ok()
    if blocked:
        return {"ok": False, "error": blocked}

    from termux_bridge import bridge_available

    if not bridge_available():
        return {"ok": False, "error": "Termux-Brücke nicht verfügbar — apps status"}

    result: dict[str, Any] = {
        "ok": True,
        "cookies": {},
        "autofill": {},
        "payments": {},
        "accounts": {},
        "passwords": {},
        "live": {},
        "limitations": [],
    }

    cookies_raw, cerr = await _pull_file(CHROME_COOKIES)
    if cookies_raw:
        result["cookies"] = parse_cookies_db(
            cookies_raw, host_filter=host_filter, limit=cookie_limit
        )
        if include_dump:
            _DUMP_DIR.mkdir(parents=True, exist_ok=True)
            (_DUMP_DIR / "Cookies").write_bytes(cookies_raw)
    else:
        result["cookies"] = {"ok": False, "error": cerr}

    web_raw, werr = await _pull_file(CHROME_WEB_DATA)
    if web_raw:
        result["autofill"] = parse_web_data(web_raw, limit=autofill_limit)
        if include_dump:
            _DUMP_DIR.mkdir(parents=True, exist_ok=True)
            (_DUMP_DIR / "WebData").write_bytes(web_raw)
    else:
        result["autofill"] = {"ok": False, "error": werr}

    acc_raw, aerr = await _pull_file(CHROME_ACCOUNT_WEB)
    if acc_raw:
        result["payments"] = parse_account_web_data(acc_raw)
        if include_dump:
            _DUMP_DIR.mkdir(parents=True, exist_ok=True)
            (_DUMP_DIR / "AccountWebData").write_bytes(acc_raw)
    else:
        result["payments"] = {"ok": False, "error": aerr}

    result["accounts"] = await list_android_accounts()
    result["passwords"] = await password_manager_status()

    if include_live:
        result["live"] = await live_decrypt_sessions(reveal=reveal_live)

    result["limitations"] = [
        "Cookie-DB: Werte v10-encrypted (Keystore) — Katalog aus DB.",
        "Live-Decrypt: Klartext aus Chrome-Prozessspeicher (chrome decrypt) wenn Chrome läuft.",
        "Login-Passwörter: keine lokale Chrome Login Data; GMS Hashes / Cloud PWM.",
        "Kartendaten: nur maskiert (last4); CVC/Nummer encrypted.",
        "Autofill/Adressen/Accounts: Klartext wenn verfügbar.",
    ]

    if include_dump:
        result["dump_dir"] = str(_DUMP_DIR)

    AuditLog.action(
        "ChromeSecrets",
        "collect",
        f"cookies={result.get('cookies', {}).get('total', 0)} "
        f"autofill={result.get('autofill', {}).get('autofill_count', 0)} "
        f"dump={include_dump} live={include_live}",
        erfolg=True,
    )
    _CACHE["at"] = time.time()
    _CACHE["data"] = result
    return result


def format_secrets_report(result: dict[str, Any], *, section: str = "all") -> str:
    if not result.get("ok"):
        return f"[Chrome Secrets] {result.get('error', 'Fehler')}"

    lines: list[str] = ["[Chrome Secrets / Device]", ""]
    section = (section or "all").lower()

    if section in {"all", "cookies", "cookie"}:
        c = result.get("cookies") or {}
        if c.get("ok"):
            lines.append(
                f"Cookies: {c.get('total', 0)} total, "
                f"zeige {c.get('returned', 0)} "
                f"(plaintext_page={c.get('plaintext_in_page', 0)}, "
                f"encrypted_page={c.get('encrypted_in_page', 0)})"
            )
            lines.append(f"  {c.get('decrypt_status', '')}")
            lines.append("  Top-Hosts:")
            for host, n in list((c.get("top_hosts") or {}).items())[:12]:
                lines.append(f"    {host}: {n}")
            lines.append("  Recent:")
            for row in (c.get("cookies") or [])[:15]:
                lines.append(
                    f"    {row.get('host')} | {row.get('name')} | {row.get('value_note')}"
                )
        else:
            lines.append(f"Cookies: Fehler — {c.get('error')}")
        lines.append("")

    if section in {"all", "autofill", "formulare"}:
        a = result.get("autofill") or {}
        if a.get("ok"):
            lines.append(f"Autofill ({a.get('autofill_count', 0)} Felder):")
            for row in (a.get("autofill") or [])[:25]:
                lines.append(
                    f"  [{row.get('count')}×] {row.get('field')}: {row.get('value')}"
                )
            if a.get("addresses"):
                lines.append("Adressen:")
                for addr in a["addresses"][:8]:
                    parts = [
                        addr.get("full_name") or f"{addr.get('first_name','')} {addr.get('last_name','')}".strip(),
                        addr.get("street_full") or addr.get("street"),
                        f"{addr.get('zip','')} {addr.get('city','')}".strip(),
                        addr.get("email"),
                        addr.get("phone"),
                    ]
                    lines.append("  · " + ", ".join(p for p in parts if p))
        else:
            lines.append(f"Autofill: Fehler — {a.get('error')}")
        lines.append("")

    if section in {"all", "payments", "karten", "cards"}:
        p = result.get("payments") or {}
        if p.get("ok"):
            lines.append(f"Karten (maskiert): {len(p.get('cards') or [])}")
            for card in (p.get("cards") or [])[:10]:
                lines.append(
                    f"  {card.get('network')} *{card.get('last_four')} "
                    f"exp {card.get('exp')} — {card.get('name')} "
                    f"{card.get('product') or card.get('bank') or ''}"
                )
            if p.get("ibans"):
                lines.append("IBANs (maskiert):")
                for ib in p["ibans"]:
                    lines.append(f"  {ib.get('masked')} {ib.get('nickname')}")
        else:
            lines.append(f"Payments: Fehler — {p.get('error')}")
        lines.append("")

    if section in {"all", "accounts", "konten"}:
        acc = result.get("accounts") or {}
        lines.append(f"Android-Accounts: {len(acc.get('accounts') or [])}")
        for row in (acc.get("accounts") or [])[:20]:
            lines.append(f"  {row.get('name')} ({row.get('type')})")
        lines.append("")

    if section in {"all", "passwords", "passwörter", "passwoerter"}:
        pw = result.get("passwords") or {}
        lines.append("Passwörter:")
        lines.append(f"  Chrome Login Data Datei: {pw.get('chrome_login_data_present')}")
        lines.append(f"  GMS password_manager.db: {pw.get('gms_db')}")
        if pw.get("accounts_with_hashes"):
            lines.append(
                f"  Hash-Einträge für: {', '.join(pw['accounts_with_hashes'][:6])}"
            )
            lines.append(f"  leak_check_entries: {pw.get('leak_check_entries')}")
        lines.append(f"  {pw.get('note', '')}")
        lines.append("")

    if section in {"all", "live", "decrypt"}:
        live = result.get("live") or {}
        if live:
            if live.get("ok"):
                lines.append(
                    f"Live-Decrypt: {live.get('count', 0)} Klartext-Werte "
                    f"(PID={ (live.get('meta') or {}).get('pid') })"
                )
                for it in (live.get("items") or [])[:20]:
                    lines.append(
                        f"  {it.get('host')} | {it.get('name')}="
                        f"{_mask_value(str(it.get('value') or ''), reveal=bool(it.get('reveal')))}"
                    )
                lines.append("  Vollständig: chrome decrypt")
            else:
                lines.append(f"Live-Decrypt: {live.get('error', '—')}")
            lines.append("")

    if result.get("dump_dir"):
        lines.append(f"Dump: {result['dump_dir']}")
        lines.append("")

    if section == "all" and result.get("limitations"):
        lines.append("Grenzen:")
        for lim in result["limitations"]:
            lines.append(f"  · {lim}")
        lines.append("  · Klartext-Cookies/Tokens: chrome decrypt (Memory)")

    return "\n".join(lines).rstrip()
