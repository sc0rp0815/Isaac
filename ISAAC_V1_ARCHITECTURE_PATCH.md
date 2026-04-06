# Isaac v1 Architecture Patch

Dieses Paket implementiert die erste tragende Schicht aus dem Entwicklungsplan:

- **Verfassungskern** (`constitution.py`)
- **Explizites Selbstmodell** (`self_model.py`)
- **Memory Blocks + Memory Events** in `memory.py`
- **Development Log** in `memory.py`
- **Lernpolitik** (`learning_policy.py`)
- **MCP-Scaffold** (`mcp_registry.py`)
- **Dashboard/API-Endpunkte** für Verfassung, Self-Model, Development-Events und Memory Blocks

## Ziel

Nicht mehr Features zuerst, sondern Formalisierung der inneren Ordnung:

1. Verfassung
2. Selbstmodell
3. Memory-Ordnung
4. Entwicklungslogik
5. Standardschicht

## Nicht vollständig umgesetzt

- Vollständige MCP-Server/Client-Implementierung
- Checkpoint/Resume-Engine für Tasks
- Vollständige Eval-Suite
- UI-Integration aller neuen Endpunkte

Diese Patch-Version ist daher **Phase 1** des Plans: Fundament statt Vollausbau.
