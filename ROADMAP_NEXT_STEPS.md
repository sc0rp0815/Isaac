# Isaac – Prioritätenliste nach dem v1-Architekturpatch

## Bereits umgesetzt in diesem Patch

- Verfassungskern (`constitution.py`)
- Explizites Selbstmodell (`self_model.py`)
- Memory Blocks in SQLite (`memory.py`)
- Development Events / Entwicklungslog (`memory.py`)
- Lernpolitik mit Risiko-Bremse (`learning_policy.py`)
- MCP-Scaffold (`mcp_registry.py`)
- Dashboard-/Monitor-Endpunkte für neue Kernobjekte
- Value/learning Hooks auf Development-Log umgebogen

## Höchste Priorität als Nächstes

### 1. Verfassung durchsetzen
- Jeden kritischen Tool-Call vor Ausführung gegen `Constitution.validate_action()` prüfen
- Blockierte Aktionen sichtbar ins Audit schreiben
- Owner-Override nur explizit und nachvollziehbar

### 2. Self-Model an reale Interaktionen anbinden
- Owner-Feedback automatisch in `relationship_state.last_owner_feedback`
- Wiederkehrende Themen in `shared_themes`
- Präferenzen aus bestätigten Interaktionen extrahieren

### 3. Task-Checkpointing in `executor.py`
- Zustände: planning / tool_pending / evaluating / learning_commit / done / failed
- Nach jedem Tool-Call Checkpoint schreiben
- Resume-Pfad für hängende oder abgestürzte Tasks

### 4. MCP wirklich implementieren
- `mcp_server.py`
- `mcp_client.py`
- Mapping von Privileges -> MCP Capabilities
- Ressourcen:
  - `resource://constitution`
  - `resource://self-model`
  - `resource://memory/blocks`
  - `resource://audit/tail`

### 5. Eval-Harness
- Governance-Evals
- Identity-Evals
- Learning-Evals
- Reliability-Evals

## Mittlere Priorität

### 6. Dashboard erweitern
- Trace Viewer
- Memory Diff Viewer
- Constitution Inspector
- Development Timeline

### 7. Skill-/Procedure-Memory
- Erfolgreiche Task-Pfade als wiederverwendbare Verfahren speichern
- Fehlerhafte Pfade markieren und abstufen

### 8. Forgetting / Decay
- Schwach bestätigte Präferenzen langsam abbauen
- Widersprochene Fakten degradieren
- Altes Entwicklungswissen archivieren statt löschen

## Niedrigere Priorität

### 9. Mehr Provider/Browser-Funktionen
- Erst nach Stabilisierung der inneren Ordnung

### 10. Multi-Agent/Handoffs
- Nur sparsam, wenn Identität stabil bleibt
