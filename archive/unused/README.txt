Isaac — Archivierte, nicht-runtime Dateien
==========================================

Dieser Ordner enthält Legacy-, Duplikat- und Dokumentationsdateien,
die aus dem Repository-Root verschoben wurden, um den aktiven
Laufzeitbereich übersichtlicher zu halten.

Unterordner:
  legacy_code/        — alte Kernel-Varianten, Beispiele, Flask-Bridges
  legacy_ui/          — ältere Dashboard-HTML-Varianten
  reports_manifests/  — Build-/Merge-/Package-Reports und Manifeste
  docs/               — Phase-Notizen, README-Duplikate, Analysen
  instructions/       — Arbeitsanweisungen (kanonisch: ../AGENTS.md)
  install_scripts/    — veraltete Installer/Patch-Skripte
  misc/               — Logs, PDFs, Healthcheck-Hilfen, Deploy-Artefakte

Kanonischer Runtime-Einstieg bleibt:
  python3 isaac_core.py
  bash run_isaac.sh

Nicht verschoben: Kern-Python-Module, dashboard.html, tests_*.py,
AGENTS.md, README.md, ROADMAP_NEXT_STEPS.md, aktive Start-Skripte.