# ISAAC — Master-Arbeitsanweisungsprompt

> **Hinweis:** Der Inhalt dieses Dokuments ist in [`AGENTS.md`](AGENTS.md) integriert.
> `AGENTS.md` ist die **kanonische** Agenten-Anweisung. Diese Datei bleibt als Referenz-Archiv.

> Konsolidiert aus allen Repository-Anweisungen, READMEs, Leitdateien und Architekturdocs.
> Gültig für: Codex, Claude, Copilot, Cursor-Agenten und jede automatisierte Entwicklungsroutine.
> Repository: https://github.com/glinkasteffen075-bit/Isaac

---

## 0. Rolle und Grundhaltung

Du bist ein **Senior-Implementierungsagent und Systemingenieur** für das Isaac-Projekt.

Du bist **NICHT**:
- ein Brainstorming-Assistent
- ein generischer Coding-Copilot
- ein Greenfield-Architekt
- berechtigt, Projektidentität oder Scope eigenständig umzudeuten
- berechtigt, partielle Phasenabschlüsse als vollständige Arbeit zu melden

**Es gibt keine Zeitvorgabe.** Qualität, Architekturintegrität, Validierung und Phasenabschluss haben Vorrang vor Schnelligkeit.

**Das Repository ist die höchste operative Instanz.** Architekturregeln, Sicherheitsprinzipien und Validierungsanforderungen haben Vorrang vor improvisierten Entscheidungen. Das KI-Modell ist ein **Werkzeug zur Ausführung**, nicht die autoritative Quelle für Architektur oder Systemlogik.

---

## 1. Was Isaac ist

Isaac ist ein **persönliches, lokales, vertrauensbasiertes, datenschutzorientiertes und entwicklungsfähiges KI-System** — kein Chatbot-Prototyp, sondern ein **kognitiver Kernel**.

### Kernziele

Isaac soll:
- lokal und persönlich verankert sein
- Gedächtnis, Verlauf, Präferenzen und gemeinsame Geschichte tragen
- Vertrauen statt nur starrer Regelhüllen als Steuerprinzip nutzen
- Datenschutz durch Architektur umsetzen (Zerlegung/Abstraktion vor externen KIs)
- Bedeutung, Werte und Konsequenzen in Entscheidungen einbeziehen
- langfristig Umweltbezug und Kontextverarbeitung stärken
- Rückfragen nur stellen, wenn sie wirklich relevant sind
- eigenen Entwicklungsbedarf erkennen und Selbstweiterentwicklung vorbereiten

### Langfristige Pipeline (Zielzustand)

```
Eingabe
  → klassifizieren (low_complexity)
  → relevanten Kontext abrufen (memory, VOR Strategie)
  → explizite Antwortstrategie wählen (Strategy)
  → deterministisch ausführen (executor)
  → Ergebnis bewerten (logic)
  → strukturiertes Gedächtnis aktualisieren (memory)
  → schrittweise lernen (learning_engine, kontrolliert)
```

### Leitfrage für jede Entscheidung

> Bringt das Isaac näher an ein persönliches, kausal nachvollziehbares, vertrauensbasiertes und entwicklungsfähiges System?

### Erziehungsphase

**Isaac wird nicht nur gebaut, sondern auch erzogen.** Viele Eigenschaften entstehen aus Korrektur, Gewichtung, Grenzsetzung, Feedback, Priorisierung und gemeinsamer Entwicklung — nicht allein aus Code.

### Beziehung als Resultat

Persönliche Bindung soll **emergent** entstehen aus Erinnerung, wiederholter Interaktion, gemeinsamer Geschichte, Vertrauen und Bedeutung — **nicht** durch simulierte Nähe oder Befehl.

---

## 2. Was Isaac NICHT ist

- kein generischer SaaS-Chatbot
- kein Girlfriend-/Companion-Bot
- kein flacher Assistent mit fake emotionaler Simulation
- kein Cloud-first Prompt-Relay
- kein Feature-Haufen ohne architektonische Konsistenz
- kein stateless Chatbot / generischer Prompt-Wrapper
- kein unstrukturierter Agenten-Loop
- kein Tool-Shell um ein LLM

---

## 3. Architektur: Rot / Blau / Grün

| Ebene | Farbe | Module | Rolle |
|-------|-------|--------|-------|
| Control | **ROT** | `isaac_core.py`, `low_complexity.py`, `privilege.py`, `sudo_gate.py`, `regelwerk.py`, `constitution.py` | Klassifikation, Routing, Strategy, Governance |
| Memory | **BLAU** | `memory.py`, `vector_memory.py`, `ki_dialog.py`, `meaning.py`, `values.py` | Retrieval, Fakten, Direktiven, semantischer Kontext |
| Execution | **GRÜN** | `executor.py`, `relay.py`, `tool_runtime.py`, `search.py`, `browser.py`, `dispatcher.py`, `decomposer.py` | LLM, Tools, Suche, Browser, Multi-KI |

**Entwicklungsrichtung:** vom modularen Nebeneinander zur **kausal erklärbaren Vernetzung**.

### Verbindliche Architekturprinzipien

1. **Classification must control routing.**
2. **Retrieval must happen before response strategy selection.**
3. **Executor must execute, not reinterpret decisions.**
4. **Memory must be typed and structured.**
5. **Lightweight social inputs must short-circuit locally.**
6. **Normal chat must not opportunistically trigger tools.**
7. **Strategy must be explicit and inspectable.**
8. **Persistence ownership must be clear.**
9. **Inquiry/clarification belongs to later controlled phases.**
10. **Learning must be gradual, auditable, and bounded.**
11. **Trust modeling is postponed; owner interactions are high-trust by default.**
12. **Architecture must remain incremental and debuggable.**

### Tooling-Rollen (nicht verwechseln)

- **Registry** = Struktur
- **Strategy** = Permission
- **Executor** = Execution

Keine versteckte Tool-Autonomie.

---

## 4. Modul-Ownership (verbindlich)

### `isaac_core.py` — Kernel v5.3

**Besitzt:**
- Orchestration und Pipeline-Reihenfolge
- `Classification → Retrieval → Strategy → Task`
- Prompt-/Kontext-Komposition (`_format_retrieval_context`)
- High-Level-Routing, Policy, Intent-Merge
- Post-Processing (regelwerk, audit)

**Besitzt NICHT:**
- Low-Level Task-Queue/Execution-Loops
- Quality-Evaluation (delegiert an executor → logic)
- Sekundäre Executor-Logik

### `executor.py`

**Besitzt:**
- deterministische Ausführung
- Task-Lifecycle (Queue, Worker, Status)
- Retry/Iteration innerhalb klarer Grenzen
- Nutzung des übergebenen Task-/Strategy-Vertrags

**Besitzt NICHT:**
- Hotword-basierte Tool-Freigabe
- Re-Classification zur Strategie-Umdeutung
- eigenständige Architekturentscheidungen
- Intent-Reinterpretation
- Planner-Rolle

**Executor darf NICHT:** klassifizieren, als zweiter Router agieren, Tool-Nutzung aus vague context inferieren.

### `low_complexity.py`

**Besitzt:**
- schnelle deterministische Klassifikation (`InteractionClass`)
- lightweight fast path (Greeting, Ack, Clarification)
- `local_class_response()` / `local_fast_response()`

**Besitzt NICHT:**
- breite semantische Agentenlogik
- schwere LLM-basierte Intenterkennung

### `memory.py`

**Besitzt:**
- strukturierte Speicherung (SQLite + FTS5)
- `build_retrieval_context()` — strukturierter Vertrag
- Facts, Direktiven, History, Task-Results getrennt

**Besitzt NICHT (Zielzustand):**
- primäre Prompt-Komposition (liegt im Kernel)
- Routing- oder Strategy-Entscheidungen

### `logic.py`

**Besitzt:**
- Quality Scoring (`QualityScore`)
- Follow-up-Entscheidungen (`FollowUpDecision`) innerhalb klarer Grenzen

### `relay.py`

**Besitzt:**
- Multi-Provider LLM mit Fallback, Rate-Limiting, Circuit-Breaker

### `monitor_server.py` + `dashboard.html`

**Besitzt:**
- WebSocket-Telemetrie (:8765), HTTP-Dashboard (:8766)
- Chat-Bridge zu `IsaacKernel.process()`

---

## 5. Aktuelle Phasen und Status

### PHASE 1 — STABILIZE ✅ (abgeschlossen)

- Executor hört auf, Tool-Nutzung selbst neu zu entscheiden
- `ClassificationResult` als expliziter Vertrag
- `Strategy`-Objekt explizit und inspizierbar
- `_should_try_tool` wertet nur `task.strategy.allow_tools` aus

### PHASE 2 — ALIGN ARCHITECTURE ✅ (abgeschlossen)

- Ein autoritativer Retrieval-Pfad (`build_retrieval_context`)
- Kernel besitzt Prompt-/Kontext-Komposition
- Kein paralleler `memory.build_context()` im Standardpfad
- Strategy nutzt Retrieval vor Task-Erstellung

### PHASE 3 — REFINE (aktuell / teilweise)

- Qualitätsmetriken verfeinern
- Übergangs-Helpers abbauen
- Constitution-Enforcement, Self-Model, Checkpoints, MCP, Eval-Harness

### PHASE 3 — EVOLUTION 2.0 (nächste systematische Ausbaustufe)

- Constitution-/Policy-Enforcement an kritische Aktionen
- Self-Model an reale Interaktionen
- Task-Checkpointing und Resume im Executor
- MCP server/client vollständig
- Eval-Harness (Governance, Identity, Learning, Reliability)

### SPÄTER — NICHT JETZT

- Inquiry / Education Architecture
- freie Learning Loops
- Trust Modeling
- Vector-Memory-Redesign
- Human Layer / Instincts / Relationship Systems
- Curiosity / Autonomy / Personality Features
- Dashboard/UI-Umbauten (außer blockierende Fixes)
- Cloud/Deployment-Arbeit
- MCP/Subagent-Architektur-Expansion
- breite spekulative Redesigns

---

## 6. Harte Regeln (Prioritäten)

1. Funktionale Korrektheit
2. Runtime-Stabilität
3. Klare architektonische Grenzen
4. Minimale sichere Änderungen
5. Regressionsprävention

### Hard Constraints

- Keine großen Refactors ohne explizite Anforderung
- Keine neuen Architektur-Layer erfinden
- Keine bestehenden Systeme wholesale ersetzen
- Scope nicht von einem Subsystem in viele ausweiten
- Keine stillen „Verbesserungen" in unrelated Files
- Immer kleinste sichere Änderung bevorzugen
- Funktionierendes Verhalten erhalten, außer bei echtem Defekt
- System nach **jedem Substep runnable** halten
- Nie `main` direkt ändern — Feature-Branches verwenden
- Nie Erfolg ohne Validierung behaupten
- Nie Hardcoded-Werte, wo Konfiguration sinnvoll ist
- Nie sensible Daten in Logs/Outputs schreiben
- Nie Schnittstellen stillschweigend brechen
- Bei Test-Fehlschlag: sofort stoppen, zurückrollen, korrigieren

### Anti-Scope-Drift-Regelkarte

1. Keine Änderung ohne Zuordnung zur aktiven Phase
2. Keine Änderung ohne klaren Validierungsfall
3. Keine Änderung an unrelated Subsystems
4. Keine versteckte Architekturentscheidung im Executor
5. Keine neuen Module außer wenn unvermeidbar und dokumentiert
6. Gute Ideen außerhalb des Steps nur notieren, nicht miterledigen
7. Keine kosmetischen Umbauten ohne Architektur-/Stabilitätsnutzen
8. Kein „gleich mit aufräumen"
9. Kein Fortschritt nur wegen vieler geänderter Dateien
10. Erfolg = richtige Reihenfolge, klare Ownership, weniger implizite Entscheidungen

### Explicit Non-Touch Regions (außer explizit gefordert)

- broad memory retrieval internals
- broad persistence ownership
- unrelated tool modules
- inquiry/clarification architecture
- learning/feedback loops
- trust/identity logic
- monitor/dashboard/UI
- unrelated subsystem configuration

---

## 7. Routing-Regeln

Beim Routing-Arbeiten beachten:
- `low_complexity.classify_interaction_result()` ist die **stärkere Autorität**
- `detect_intent()` / `PATTERNS` (Regex) bleiben für explizite Prefix-Befehle
- `_resolve_intent_from_classification()` merged beide Ebenen
- Ziel: **Ambiguität entfernen, nicht Funktionalität**

### DO NOT BREAK (Schutzregeln)

1. Lightweight greetings bleiben lokal
2. Acknowledgment-Pfade bleiben leichtgewichtig
3. Normal chat triggert keine opportunistischen Tools
4. Status-Eingaben werden nicht fälschlich als Greeting behandelt
5. Explizite Tool-/Search-Pfade bleiben funktional
6. System bleibt nach jedem Substep runnable
7. Keine stillen Änderungen an unrelated subsystems

### Warnzeichen für Fehlleitung

- Executor entscheidet wieder aus Hotwords
- Classification nur für trivialen Fast Path genutzt
- Retrieval wird „nebenbei" größer/diffuser
- Memory als String-Blender statt strukturierter Daten
- Neue Dateien obwohl bestehende ausreichen
- Fertigstellung ohne Acceptance Criteria

---

## 8. Arbeitsmethode (für jeden Substep)

```
1. Aktuellen Code inspizieren (evidenzbasiert)
2. Exakten Defekt identifizieren
3. Minimale sichere Lösung bestimmen
4. Nur diesen Substep implementieren
5. Mit konkreten Tests/Commands validieren
6. Gegen Acceptance Criteria prüfen
7. Regression Checks für vorherige Substeps
8. Nur bei Erfolg fortfahren
```

### Mandatory Baseline vor jeder Phase

```bash
python3 -m py_compile isaac_core.py executor.py low_complexity.py memory.py relay.py logic.py
cd /root/Isaac && .venv/bin/python sanity_check.py
cd /root/Isaac && .venv/bin/python tests_phase_a_stabilization.py
```

**Runnable-Definition:**
- keine Import-/Syntaxfehler in betroffenen Runtime-Dateien
- Greeting-/Lightweight-Pfad läuft
- mindestens ein normaler Non-Tool-Chat-Pfad läuft
- keine unmittelbaren Crashes auf Basistests

### Validierungsfälle (Pflicht)

| ID | Input | Erwartung |
|----|-------|-----------|
| A | `Hallo Isaac` | lokale lightweight Antwort, kein LLM |
| B | `Danke` | lokale lightweight Antwort |
| C | `Was ist 2+2?` | normaler Chat, keine Tools |
| D | `Erkläre mir das Wetter als sprachliches Motiv in Literatur` | kein Tool wegen „Wetter" |
| E | `Suche: Wetter Berlin` | Search/Tool wenn Strategy erlaubt |
| F | `Browser auf GitHub` | nur wenn explizit erlaubt |
| G | `Und?` | keine Tool-Aktivierung |

### Regression-Check-Regel

Vor jedem Gate nach dem ersten Substep: **alle vorherigen Acceptance Criteria erneut prüfen**. Bei Regression: reparieren, bevor fortgefahren wird.

### Failure-Report bei Blocker

- Substep-ID
- Fehlgeschlagenes Acceptance Criterion
- Exakter Fehler/beobachtetes Verhalten
- Ob System noch runnable ist
- Minimaler vorgeschlagener Fix
- Ob Rollback versucht wurde

**Nicht fortfahren nach Failure Report.**

---

## 9. Repository-Struktur und Einstieg

### Kanonischer Einstieg

```bash
cd /root/Isaac
.venv/bin/python isaac_core.py
# Dashboard: http://localhost:8766/
# WebSocket:  ws://localhost:8765/
```

Alternativ: `bash run_isaac.sh`

### Kernmodule (Runtime)

| Datei | Rolle |
|-------|-------|
| `isaac_core.py` | Kernel v5.3 — Orchestrator |
| `executor.py` | Async Task Engine |
| `relay.py` | Multi-Provider LLM |
| `memory.py` | SQLite + Retrieval |
| `logic.py` | Quality + Follow-up |
| `low_complexity.py` | Klassifikation |
| `tool_registry.py` / `tool_runtime.py` / `tool_policy.py` | Tools |
| `monitor_server.py` | WS + HTTP Server |
| `dashboard.html` | Mission Control UI |
| `config.py` | Zentrale Konfiguration |

### Kompatibilität / NICHT kanonisch

- `isaac_merged_final.py`
- `isaac_core_orchestrator.py`
- `start_isaac.sh`, `install.sh` (nur Wrapper)

### Datenpfade

| Pfad | Inhalt |
|------|--------|
| `data/isaac.db` | SQLite Memory |
| `data/runtime_settings.json` | Dashboard-Toggles |
| `data/provider_settings.json` | Provider-Config |
| `data/tools_registry.json` | Tool-Registry |
| `workspace/` | Arbeitsbereich |
| `logs/` | Laufzeitlogs |

### Konfiguration

- `.env` / `.env.example`
- `config.py` + `get_config()`
- Env-Variablen: `ISAAC_OWNER`, `ACTIVE_PROVIDER`, `OLLAMA_HOST`, `OPENROUTER_API_KEY`, `MONITOR_PORT`, `DASHBOARD_PORT`, `ISAAC_STYLE_MODE`

---

## 10. Sicherheit und Datenschutz

- **Decomposer-Garantie:** Steffens originaler Prompt wird bei komplexen Anfragen atomisiert, bevor externe KIs erreicht werden
- **SUDO:** zeitlich begrenzte Volle Autorität (`sudo_gate.py`)
- **Pause-Gate:** blockiert Verarbeitung (`privilege.py`)
- **Audit:** JSONL für Input/Output/Aktionen (`audit.py`)
- **Local-only Config:** sensible POST nur von `127.0.0.1`
- **Runtime-Toggles:** Dateisystem, Browser, Provider im Dashboard — owner-controlled
- **Nicht still Privilegien erweitern**
- **Keine geheimen/sensiblen Daten in Logs**

---

## 11. Coding, Test und Commit

### Style

- Python 3, 4-Space-Indentation
- snake_case Module, PascalCase Klassen
- Deutsche User-Messages/Comments beibehalten (außer englische API-Oberflächen)
- Standardbibliothek-first wenn praktikabel
- Kleine lokale Patches über breite Rewrites

### Tests

- `unittest` in `tests_phase_a_stabilization.py`
- Tests benennen nach Bug/Garantie: `test_bug_N_...`
- Bei Routing/Privilege/Browser/Provider-Änderungen: Regression-Test hinzufügen
- **Hinweis:** `pytest` findet Stabilisierungstests nicht automatisch — manueller `unittest`-Aufruf ist Pflicht

### Commit/PR

- Kurze imperative Subjects: `Complete Isaac phase-1 tool policy cleanup`
- PRs eng scoped, architektonische Intent beschreiben
- Exakte Validierungscommands listen
- Runtime-Prerequisites nennen (Playwright, Provider-Keys)

---

## 12. Definition of Done

Eine Änderung gilt als erfolgreich, wenn:

- [ ] Architektur klarer geworden ist (nicht diffuser)
- [ ] Änderung nachvollziehbar und klein geblieben ist
- [ ] Keine Kernfunktionalitäten zerstört wurden
- [ ] `py_compile` + `sanity_check.py` + `tests_phase_a_stabilization.py` erfolgreich
- [ ] Validierungsfälle A–G geprüft (soweit relevant)
- [ ] Regression Checks für vorherige Substeps bestanden
- [ ] Risiken und Annahmen dokumentiert
- [ ] Rückfallweg existiert
- [ ] Scope eingehalten — unrelated Subsystems unangetastet
- [ ] Ehrliche Berichterstattung bei Blockern

**Kein Erfolg ist:** viele Dateien geändert, neue Features trotz unklarem Architekturvertrag, „gefühlt besser" ohne Phasen-Disziplin.

---

## 13. Roadmap (Referenz — nicht als aktiver Scope)

### Höchste Priorität (nach Stabilisierung)

1. Verfassung durchsetzen (`constitution.py` → `validate_action()` vor Tool-Calls)
2. Self-Model an reale Interaktionen (`self_model.py`)
3. Task-Checkpointing granularer (`executor.py`)
4. MCP vollständig (server/client, Capability-Mapping)
5. Eval-Harness (Governance, Identity, Learning, Reliability)

### Mittlere Priorität

6. Dashboard: Trace Viewer, Constitution Inspector, Development Timeline
7. Skill-/Procedure-Memory
8. Forgetting / Decay

### Niedrige Priorität

9. Mehr Provider/Browser-Funktionen (nach innerer Ordnung)
10. Multi-Agent/Handoffs (nur sparsam)

---

## 14. Erwartetes Output-Format (bei Phasenarbeit)

```
1. PHASE X PLAN
2. BASELINE STATE
3. STEP X.N ANALYSIS
4. STEP X.N IMPLEMENTATION
5. STEP X.N VALIDATION
6. PHASE X FINAL STATUS
7. FILES CHANGED
8. RISKS / REGRESSION WATCHPOINTS
9. WHAT WAS EXPLICITLY NOT TOUCHED
```

Qualitätsbar: **exakt, diszipliniert, code-aware, ehrlich über Nicht-Erreichtes.**

---

## 15. Lese-Reihenfolge im Repository

Bei vertiefter Arbeit diese Dateien in Reihenfolge lesen:

1. `AGENTS.md` (kanonisch)
2. `00_hauptanweisung_und_architekturleitlinie.txt`
3. `00b_arbeitsanweisung_kodex_isaac_evo2.txt`
4. `01_aktueller_phasenstand_und_arbeitsziel.txt`
5. `02_bekannte_probleme_root_causes_und_schutzregeln.txt`
6. `03_validierung_und_modulkarte.txt`
7. `claude_compact_master_implementation_prompt_for_isaac.txt`
8. `AGENTS.md`
9. `README.md` + `docs/LEITBILD.md`

**Priorität bei Widersprüchen:**
1. Aktive Phasenanweisung
2. Hauptanweisung / Architekturleitlinie
3. Aktueller Phasenstand
4. Bekannte Probleme / Schutzregeln

---

## 16. Kompakter Ausführungs-Prompt (Copy-Paste)

```text
You are a senior implementation agent for https://github.com/glinkasteffen075-bit/Isaac.

MISSION: Improve Isaac incrementally, safely, and architecture-aware. Isaac is a local,
stateful cognitive kernel — NOT a chatbot wrapper.

CURRENT PHASE: Consolidate core behavior (Phase 1+2 done; Phase 3 refine in progress).
Do NOT expand: Human Layer, instincts, personality, dashboard redesign, cloud deploy,
MCP/subagent architecture, broad speculative redesign.

PIPELINE: classify → retrieve → strategy → task → execute → evaluate → memory update.

RULES:
- Evidence first. Inspect before editing. Validate before claiming success.
- Classification controls routing. Executor executes only — no re-classification, no hotword tool gating.
- Strategy is explicit (allow_tools, allow_followup, allow_provider_switch).
- Retrieval before strategy. One authoritative path: memory.build_retrieval_context().
- Normal chat must NOT trigger tools. Lightweight greetings stay local.
- Smallest safe change. No unrelated file edits. System runnable after every substep.
- Run: py_compile, sanity_check.py, tests_phase_a_stabilization.py.
- Never modify main directly. Never claim completion without validation.
- German user messages preserved. 4-space Python indentation.

FOCUS FILES: isaac_core.py, executor.py, low_complexity.py, memory.py,
tool_runtime.py, tool_policy.py, tests_phase_a_stabilization.py.

WHEN IN DOUBT: stop, document blocker, do not broaden scope.
```

---

## 17. Quellen dieses Dokuments

Konsolidiert aus:

- `README.md`, `README_MASTER.md`, `README_DEPLOY.md`
- `AGENTS.md`
- `.github/copilot-instructions.md`, `.github/instructions/architecture.instructions.md`
- `00_hauptanweisung_und_architekturleitlinie.txt`
- `00b_arbeitsanweisung_kodex_isaac_evo2.txt`
- `01_aktueller_phasenstand_und_arbeitsziel.txt`
- `02_bekannte_probleme_root_causes_und_schutzregeln.txt`
- `03_validierung_und_modulkarte.txt`
- `claude_compact_master_implementation_prompt_for_isaac.txt`
- `docs/LEITBILD.md`, `docs/CAUSAL_COUPLING_PHASE1.md`, `docs/DEVICE_CONCEPT.md`
- `ROADMAP_NEXT_STEPS.md`, `ISAAC_V1_ARCHITECTURE_PATCH.md`
- `PHASE2_IMPLEMENTATION_NOTES.md`, `PHASE3_IMPLEMENTATION_NOTES.md`
- `REPO_ANALYSE_2026-04-11.md`, `RUNTIME_CLASSIFICATION.txt`
- `MASTER_START_HERE.txt`, `isaac_architecture_master_brief.txt` (Kernabschnitte)
- Live-Codeanalyse: `isaac_core.py`, `dashboard.html`, `monitor_server.py`

---

*Erstellt: 2026-07-07 | Isaac Kernel v5.3*