from __future__ import annotations
import importlib
import json
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED_FILES = [
    "isaac_core.py", "relay.py", "monitor_server.py", "requirements.txt",
    "config.py", "executor.py", "memory.py", "logic.py",
]
OPTIONAL_FILES = [
    ".env", ".env.example", "dashboard.html", "dashboard_live.html",
    "start_isaac.sh", "run_isaac.sh", "background_loop.py",
]
IMPORTS = [
    "config", "audit", "memory", "logic", "privilege", "sudo_gate",
    "decomposer", "dispatcher", "search", "regelwerk", "empathie",
    "watchdog", "relay", "executor", "browser", "ki_dialog",
    "ki_skills", "background_loop", "monitor_server", "tool_registry",
    "secrets_store", "tool_runtime", "learning_engine", "trust_engine",
    "dashboard_api", "isaac_core",
]
OPTIONAL_DEPS = ["aiohttp", "websockets", "chromadb"]
PORTS = [8765, 8766, 8875]


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    report: dict[str, object] = {
        "root": str(ROOT),
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "required_files": {},
        "optional_files": {},
        "imports": {},
        "optional_dependencies": {},
        "local_ports": {},
        "warnings": [],
        "status": "ok",
    }

    missing_required = []
    for rel in REQUIRED_FILES:
        ok = (ROOT / rel).exists()
        report["required_files"][rel] = ok
        if not ok:
            missing_required.append(rel)
    for rel in OPTIONAL_FILES:
        report["optional_files"][rel] = (ROOT / rel).exists()

    for mod in IMPORTS:
        try:
            importlib.import_module(mod)
            report["imports"][mod] = "ok"
        except Exception as e:
            report["imports"][mod] = f"ERROR: {e}"
    import_failures = [k for k, v in report["imports"].items() if v != "ok"]

    for dep in OPTIONAL_DEPS:
        try:
            importlib.import_module(dep)
            report["optional_dependencies"][dep] = "installed"
        except Exception as e:
            report["optional_dependencies"][dep] = f"missing: {e}"

    for port in PORTS:
        report["local_ports"][str(port)] = "open" if port_open(port) else "closed"

    env_path = ROOT / ".env"
    if not env_path.exists() and (ROOT / ".env.example").exists():
        report["warnings"].append(".env fehlt; .env.example vorhanden")
    if not (ROOT / "data").exists():
        report["warnings"].append("data/ fehlt")

    if missing_required or import_failures:
        report["status"] = "error"
    elif report["warnings"]:
        report["status"] = "warning"

    out = ROOT / "HEALTHCHECK_REPORT.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Isaac healthcheck status: {report['status']}")
    print(f"Report: {out}")
    if missing_required:
      print("Missing required files:")
      for item in missing_required:
        print(f"- {item}")
    if import_failures:
      print("Import failures:")
      for item in import_failures:
        print(f"- {item}: {report['imports'][item]}")
    if report["warnings"]:
      print("Warnings:")
      for item in report["warnings"]:
        print(f"- {item}")
    return 0 if report["status"] != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
