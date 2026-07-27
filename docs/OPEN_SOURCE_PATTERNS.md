# Open-Source-Muster für Isaac (bounded)

Isaac importiert **keine** Agent-Frameworks wholesale. Stattdessen werden erprobte
Ideen als *kleine, lokale Muster* auf bestehende Module abgebildet.

## Was wir bewusst nicht übernehmen

| Projekt | Warum nicht wholesale |
|---------|------------------------|
| LangGraph / CrewAI / OpenHands | Fremder Orchestrator würde Kernel-Pipeline ersetzen |
| Mem0 SaaS / Zep Cloud | Cloud-first, widerspricht local-first Datenschutz |
| SemaClaw Multi-Agent | MCP/Subagent-Expansion ist Out-of-Scope |
| Next.js SaaS-Boilerplates (`web/`) | Nicht Kernel-Kern; unangetastet |

## Übernommene Muster (Isaac-Mapping)

### 1. Think ≠ Act (OpenParallax)

- **Muster:** Planungsprozess darf Execution nicht neu interpretieren.
- **Isaac:** Classification + Strategy im Kernel; Executor führt nur Task-/Strategy-Vertrag aus.
- **Absicherung:** Regression `test_e2_executor_does_not_reclassify_input`.

### 2. Observability-Phasen (Langfuse-ähnlich)

- **Muster:** Explizite Spans/Phasen für Routing und Bewertung.
- **Isaac:** `DecisionTrace` / `TracePhase` inkl. `evaluation` und `learning`.
- **Kein** externes Tracing-Backend.

### 3. Typed / Local Memory (Letta Blocks, Mem0 OpenMemory)

- **Muster:** Strukturierte Memory-Einheiten, local-first Retrieval.
- **Isaac:** Memory Blocks + `build_retrieval_context` + Procedure Memory.
- **Bounded Selection:** Reliability + Keyword-Overlap → Tool-Hints (`tool_runtime`).

### 3b. External Memory Adapters (bounded) — Mem0 / Cognee / Letta

Optional BLAU-Ergänzung unter `external_memory/`. **Kein** Ersatz von `memory.py`.

| System | Rolle in Isaac | Default | Write |
|--------|----------------|---------|-------|
| Mem0 Platform API + OSS | Präferenz/Fakten-Hints → Retrieval | ON wenn `MEM0_API_KEY` | auto-write bei Key + Score-Gate |
| Cognee | Graph-Memory (`remember`/`recall`) → `semantic_context` | OFF | wie Mem0 |
| Letta Code CLI + Cloud API | Memory-Hints + Companion, **nicht** Orchestrator | OFF | archival write nur mit Write-Flag; `letta: …` explizit |
| Open Interpreter (Codex harness) | Companion CLI, **nicht** Orchestrator | OFF | nur `oi:` / `interpreter: …`; Sandbox default `read-only` |

**Flags:** `ISAAC_MEM0_ENABLED`, `ISAAC_COGNEE_ENABLED`, `ISAAC_LETTA_ENABLED`, `ISAAC_OPEN_INTERPRETER_ENABLED`, `ISAAC_EXTERNAL_MEMORY_WRITE`.  
**Gates:** `ISAAC_EXTERNAL_MEMORY_SEARCH_TIMEOUT`, `…_SEARCH_MIN_SCORE`, `…_MIN_SCORE` (write), `…_MAX_HIT_CHARS`.  
**Install:** `bash scripts/install_external_memory.sh` / `requirements-memory-extra.txt`; OI: Binary `interpreter` + `docs/OPEN_INTERPRETER.md`.  
**Cloud:** Mem0 Platform: `MEM0_API_KEY` (+ optional `ISAAC_MEM0_ALLOW_CLOUD=1`, auto wenn Key gesetzt).  
REST-Fallback ohne SDK (`api.mem0.ai`). Local OSS nur ohne Platform-Key (Ollama+Chroma).  
Cognee: `COGNEE_BASE_URL` + `COGNEE_API_KEY` + `ISAAC_COGNEE_ALLOW_CLOUD=1`. Seed: `scripts/seed_cognee_cloud.py`.  
Letta: `LETTA_API_KEY` + `ISAAC_LETTA_ALLOW_CLOUD=1` (+ optional `LETTA_AGENT_ID`) — siehe [LETTA.md](LETTA.md).  
**Fail-soft:** Timeout / fehlende Packages / Credits → leere Hits oder klarer Fehler, Kernel bleibt runnable.  
**Bridge:** parallel search, score-normalize, Letta kind labels, write path Mem0+Cognee+Letta archival.

### 4. Tool/Skill Schema (Hermes-Agent-Kompatibilität)

- **Muster:** Einheitliche Tool-Metadaten und Permission-Felder.
- **Isaac:** `hermes_compat.py` (bereits im Main).

### 5. Confirmation / Safety Gates (PermissionBridge-Idee)

- **Muster:** Explizite Freigabe vor riskanten Aktionen.
- **Isaac:** `constitution.validate_action`, `constitution_override`, `privilege`, `sudo_gate`.

### 6. Think/Act Separation an Execution-Grenzen (OpenParallax-vertieft)

- **Muster:** Execution-Pfade dürfen Policy nicht umgehen.
- **Isaac (E2.0):**
  - Shell: `computer_use._constitution_gate_shell` + destruktive Marker → `protect_user`
  - Tools: `tool_runtime.constitution_gate_for_tool` mappt Shell-Tools auf `system_command`
  - Packages: `updater.apply_package` / `rollback_last_backup` → `modify_config` braucht Owner
  - Credentials: `credential_access` + Browser-Auto-Login → Owner-only Constitution
  - Privilege: kritische `authorize()`-Aktionen laufen durch dasselbe Verfassungs-Gate
  - Konsolidierung: `critical_action_gate()` + `CONSTITUTION_BOUNDARIES` Inventar

## Auswahlregel für künftige Übernahmen

1. Passt es zur Pipeline `classify → retrieve → strategy → task → execute → evaluate → memory`?
2. Bleibt Ownership der Module (ROT/BLAU/GRÜN) klar?
3. Ist die Änderung klein, testbar und ohne neuen Framework-Layer?
4. Verletzt sie Do-NOT-expand (Human Layer, Dashboard-Redesign, Cloud, MCP-Subagents)?

Wenn nein → nur in `05_evolution2_checklist.txt` notieren, nicht implementieren.

**Watchlist (GitHub-Scan, Tier A–E):** `docs/GITHUB_WATCHLIST.md`
