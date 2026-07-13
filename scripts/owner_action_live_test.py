#!/usr/bin/env python3
"""Live-Test für Owner-Action Erkennung und Ausführung.

Lokal und auf Termux (S8+) nutzbar:

  ISAAC_DISABLE_VECTOR_MEMORY=1 python3 scripts/owner_action_live_test.py
  ISAAC_DISABLE_VECTOR_MEMORY=1 python3 scripts/owner_action_live_test.py --live
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("ISAAC_DISABLE_VECTOR_MEMORY", "1")
os.environ.setdefault("ISAAC_PRIVILEGE_MODE", "admin")


DETECT_CASES: list[tuple[str, str]] = [
    ("Isaac, suche bei Google Fotos raus über gelbe Blumen", "photos_search"),
    ("räume downloads auf", "filesystem_cleanup"),
    ("zeig mir den wlan status vom router", "wlan_status"),
    ("schreib email an test@mail.de", "email_compose"),
    ("was steht heute im kalender", "calendar_open"),
    ("navigiere nach Berlin", "maps_navigate"),
    ("übersetze hallo nach englisch", "translate"),
    ("zeige wetter in München", "weather"),
    ("spiele auf spotify test song", "media_play"),
    ("timer 2 minuten", "timer"),
    ("schalte wlan aus", "device_toggle"),
    ("suche auf amazon nach kabel", "shopping_search"),
    ("git status", "git_command"),
    ("isaac status", "isaac_ops"),
    ("finde datei config.py in ~", "find_files"),
    ("lies vor: Test", "tts"),
    ("ping 127.0.0.1", "network_test"),
    ("wo bin ich", "device_status"),
    ("wie spät ist es", "device_status"),
    ("zeige prozesse", "device_status"),
    ("hotspot an", "device_toggle"),
    ("speedtest", "network_test"),
    ("lies datei ~/.bashrc", "file_operation"),
    ("zeige security toolkit", "security_toolkit"),
    ("sync security toolkit", "security_toolkit"),
    ("installiere metasploit", "security_toolkit"),
    ("nutze nmap status", "security_toolkit"),
    ("scanne mein wlan mit wifite", "security_toolkit"),
    ("analysiere mein wlan", "security_toolkit"),
    ("prüfe meinen router", "security_toolkit"),
    ("nethunter status", "security_toolkit"),
    ("erkläre mir das Wetter als sprachliches Motiv in Literatur", ""),
]

# Sichere Ausführung (kein Destruktives, kein Netz-Heavy)
EXEC_CASES: list[tuple[str, bool]] = [
    ("isaac status", True),
    ("git status", True),
    ("zeige akku status", True),
]

# Nur mit --live (Termux-API / Gerät)
LIVE_CASES: list[tuple[str, bool]] = [
    ("isaac status", True),
    ("zeige wlan status", True),
    ("ping 127.0.0.1", True),
    ("wie voll ist mein speicher", True),
]


def _is_termux() -> bool:
    return Path("/data/data/com.termux").exists() or os.environ.get("ISAAC_RUNTIME_ENV") == "termux"


def _is_s8_device() -> bool:
    try:
        mounts = Path("/proc/mounts").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "by-name/USERDATA" in mounts or os.environ.get("ISAAC_RUNTIME_ENV") == "s8"


async def run_detect() -> tuple[int, int]:
    from owner_action import detect_owner_action

    ok = 0
    fail = 0
    print("\n=== Erkennung ===")
    for text, expected in DETECT_CASES:
        action = detect_owner_action(text)
        kind = action.kind if action else ""
        if expected:
            passed = kind == expected
        else:
            passed = action is None
        mark = "OK" if passed else "FAIL"
        if passed:
            ok += 1
        else:
            fail += 1
        print(f"  [{mark}] {text[:52]:52} → {kind or '(none)'}")
        if not passed:
            print(f"         erwartet: {expected or '(none)'}")
    print(f"\nErkennung: {ok} OK, {fail} FAIL")
    return ok, fail


async def run_execute(cases: list[tuple[str, bool]], label: str) -> tuple[int, int]:
    from owner_action import detect_owner_action, execute_owner_action

    ok = 0
    fail = 0
    print(f"\n=== Ausführung ({label}) ===")
    for text, _ in cases:
        action = detect_owner_action(text)
        if not action:
            print(f"  [FAIL] Keine Aktion: {text}")
            fail += 1
            continue
        try:
            result, success = await execute_owner_action(action)
            preview = (result or "").splitlines()[0][:80]
            mark = "OK" if success else "WARN"
            if success:
                ok += 1
            else:
                fail += 1
            print(f"  [{mark}] {action.kind:18} | {preview}")
        except Exception as exc:
            fail += 1
            print(f"  [FAIL] {action.kind}: {exc}")
    print(f"\nAusführung ({label}): {ok} OK, {fail} FAIL/WARN")
    return ok, fail


async def run_kernel_smoke() -> tuple[int, int]:
    from isaac_core import IsaacKernel

    cmds = ["Hallo Isaac", "isaac status", "zeige wlan status"]
    ok = 0
    fail = 0
    print("\n=== Kernel Smoke (admin) ===")
    kernel = IsaacKernel()
    for cmd in cmds:
        try:
            out = await kernel.process(cmd)
            preview = (out or "").splitlines()[0][:72]
            is_greeting = cmd.startswith("Hallo")
            passed = bool(out) and (is_greeting or "[Owner]" in out or "Isaac" in out)
            mark = "OK" if passed else "WARN"
            if passed:
                ok += 1
            else:
                fail += 1
            print(f"  [{mark}] {cmd[:40]:40} → {preview}")
        except Exception as exc:
            fail += 1
            print(f"  [FAIL] {cmd}: {exc}")
    print(f"\nKernel: {ok} OK, {fail} FAIL/WARN")
    return ok, fail


async def main() -> int:
    parser = argparse.ArgumentParser(description="Owner-Action Live-Test")
    parser.add_argument("--live", action="store_true", help="Termux-Live-Ausführung (WLAN, Akku, …)")
    parser.add_argument("--kernel", action="store_true", help="IsaacKernel process() Smoke-Test")
    parser.add_argument("--detect-only", action="store_true", help="Nur Erkennung testen")
    args = parser.parse_args()

    print("Owner-Action Live-Test")
    print(f"  ROOT:     {ROOT}")
    print(f"  Termux:   {_is_termux()}")
    print(f"  S8/Linux: {_is_s8_device()}")
    print(f"  Admin:    {os.environ.get('ISAAC_PRIVILEGE_MODE', 'user')}")

    d_ok, d_fail = await run_detect()
    total_fail = d_fail

    if not args.detect_only:
        e_ok, e_fail = await run_execute(EXEC_CASES, "sicher")
        total_fail += e_fail

        if args.live:
            if not _is_termux():
                print("\n[Hinweis] --live ohne Termux: einige Befehle schlagen erwartbar fehl.")
            l_ok, l_fail = await run_execute(LIVE_CASES, "live")
            total_fail += l_fail

        if args.kernel:
            k_ok, k_fail = await run_kernel_smoke()
            total_fail += k_fail

    print("\n" + ("=" * 50))
    if total_fail:
        print(f"ERGEBNIS: {total_fail} Fehler/Warnungen")
        return 1
    print("ERGEBNIS: Alle Tests bestanden")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))