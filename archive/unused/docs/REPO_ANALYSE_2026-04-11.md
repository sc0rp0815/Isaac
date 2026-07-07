# Repository-Analyse (Stand: 2026-04-11)

## Ziel dieser Analyse
Diese Notiz fasst eine schnelle, aber vollständige Repository-Durchsicht auf Dateiebene zusammen und priorisiert die aus meiner Sicht sinnvollsten nächsten Änderungen.

## Kurzfazit
- Die inhaltliche Vision ist klar und konsistent dokumentiert.
- Es gibt bereits fokussierte Stabilisierungstests, aber die automatische Test-Discovery ist derzeit nicht sauber angebunden.
- Ein paar Architektur-/Infrastruktur-Baustellen sind explizit bekannt und sollten vor Feature-Expansion erledigt werden.

## Beobachtungen

### 1) Testbarkeit / CI-Reife
- `pytest` findet aktuell keine Tests automatisch (`no tests ran`), obwohl ein valider Testsatz vorhanden ist.
- `tests_phase_a_stabilization.py` läuft mit `unittest` erfolgreich (8/8).

**Konsequenz:** Bei CI/PR-Checks besteht Risiko, dass Green-Checks trotz ungetesteter Änderungen auftreten, wenn nur `pytest` ausgeführt wird.

### 2) Routing-/Web-Komponente mit offenen TODOs
In `web_urldispatcher.py` sind mehrere TODOs an zentralen Stellen enthalten:
- abstrakte Methoden noch nicht vollständig umgesetzt
- fehlende Methoden in Prefix-Ressource
- fehlendes Caching bei versionierter Datei-URL-Erzeugung

**Konsequenz:** Potenzielle Laufzeit-/Wartbarkeitsrisiken in einem zentralen I/O-Bereich.

### 3) Roadmap ist bereits korrekt priorisiert
`ROADMAP_NEXT_STEPS.md` priorisiert genau die richtigen Blöcke für den aktuellen Reifegrad:
1. Verfassungserzwingung
2. Self-Model-Anbindung an reale Interaktionen
3. Task-Checkpointing
4. MCP-End-to-End
5. Eval-Harness

**Konsequenz:** Es braucht vor allem Umsetzungsdisziplin, nicht neue Zielsetzung.

### 4) Repo-Hygiene / Struktur
Es existieren sehr viele Readmes, Manifeste, Reports und Start-/Install-Skripte parallel.

**Konsequenz:** Hohe Einstiegshürde, erhöhter Pflegeaufwand, Gefahr von Wissensdrift zwischen Dateien.

## Empfohlene Änderungen (priorisiert)

### P0 – sofort
1. **Test-Discovery fixen**
   - Entweder Datei in `test_*.py` umbenennen oder `pytest.ini` ergänzen (`python_files = tests_phase_*.py`).
   - Ziel: `pytest -q` muss zuverlässig denselben Basisschutz liefern wie der manuelle `unittest`-Aufruf.

2. **Minimal-CI einführen/verschärfen**
   - Pflichtchecks: `python -m compileall -q .` + `pytest -q`.
   - Optional zusätzlich Ruff/Black/Mypy je nach gewünschter Strenge.

### P1 – kurzfristig
3. **`web_urldispatcher.py` TODOs abarbeiten**
   - Fehlende abstrakte Methoden in `Resource`/`PrefixResource` sauber ergänzen.
   - Caching für Datei-Hashes bei Static-Assets einführen (inkl. invalidation-Strategie).

4. **Roadmap-Punkt 1 (Verfassungserzwingung) technisch schließen**
   - Tool-Policy zentral vor Ausführung prüfen.
   - Blockierte Aktionen auditierbar protokollieren.

### P2 – danach
5. **Dokumentationskonsolidierung**
   - Ein zentrales Einstiegspapier (`README.md`) + dedizierte Unterordner (`docs/architecture`, `docs/deploy`, `docs/changelog`).
   - Veraltete/duplizierte Reports archivieren.

6. **Repo-Topologie vereinheitlichen**
   - Python-Paketstruktur einführen (z. B. `src/isaac/...`) für klare Modulgrenzen und robustere Imports.

## Pull-/PR-Status
- Aus dem lokalen Repository ist **kein Remote** konfiguriert.
- `gh` (GitHub CLI) ist hier nicht verfügbar/konfiguriert.

**Folge:** Offene Pull Requests lassen sich in dieser Umgebung nicht verlässlich abrufen.
Wenn du willst, kann ich im nächsten Schritt eine kleine Checkliste liefern, wie du lokal oder in GitHub in 30 Sekunden offene PRs validierst.
