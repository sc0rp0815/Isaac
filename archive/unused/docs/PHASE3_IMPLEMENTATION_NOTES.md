# Phase 3 – Implementierungsnotizen

## Neu
- `mcp_registry.py` zu einer ausführbaren Registry erweitert
- `mcp_server.py` hinzugefügt (HTTP-Bridge für MCP-nahe Ressourcen/Tools)
- `mcp_client.py` hinzugefügt (einfacher HTTP-Client)
- `evals/learning_eval.py` hinzugefügt
- `evals/reliability_eval.py` hinzugefügt

## Geändert
- `isaac_core.py`
  - MCP-Ressourcen und -Tools besitzen jetzt echte Handler
  - Ressourcen: constitution, self-model, directives, audit tail, memory blocks
  - Tools: query_memory, start_task, search_web, run_browser_action
- `memory.py`
  - `list_checkpoints(task_id, limit)` ergänzt
- `dashboard_api.py`
  - Evals-Endpunkte
  - MCP-Resource-Read / Tool-Invoke Endpunkte
  - Memory-Block-Detail und Checkpoint-Liste
- `monitor_api.py`
  - MCP-Capabilities + Eval-Status im Monitor-State
- `app_bridge.py` / `integration_example.py`
  - MCP-Blueprint registriert
- `evals/eval_runner.py`
  - Governance, Identity, Learning, Reliability

## Getestet
- Python-Compile der geänderten Dateien
- Kernel-Initialisierung
- MCP-Registry (read_resource / invoke_tool)
- Eval-Runner erfolgreich

## Hinweis
- Flask war in der Container-Umgebung nicht installiert, daher wurden die HTTP-Blueprints per Compile geprüft, aber nicht live mit einem Flask-Testclient ausgeführt.
- Die eigentliche MCP-Schicht ist bewusst leichtgewichtig gehalten: kompatible Ideen (Tools, Resources, Capabilities, Invoke/Read), aber kein vollständiger JSON-RPC-Transport.
