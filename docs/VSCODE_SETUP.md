# VS Code / Cursor — Isaac Workspace

Konfiguration liegt unter `.vscode/` und `isaac.code-workspace`.

## Auf dem PC (empfohlen)

1. Repo klonen oder diesen Tree öffnen  
2. **File → Open Workspace from File…** → `isaac.code-workspace`  
   oder Ordner `/root/isaacnew` / dein Clone öffnen  
3. Empfohlene Extensions installieren (Popup oder Extensions-Panel)  
4. Python-Interpreter: `.venv/bin/python` wählen  
5. Debug: **Isaac Core** (F5) → Dashboard `http://127.0.0.1:8766`

### Tasks (Ctrl/Cmd+Shift+B / Terminal → Run Task)

| Task | Zweck |
|------|--------|
| `Isaac: py_compile core` | Syntax-Check Kernmodule |
| `Isaac: sanity_check` | Sanity |
| `Isaac: unittest core modules` | Pflicht-Unittests |
| `Isaac: start (background)` | Kernel starten |
| `Isaac: healthz` | Health prüfen |
| `Isaac: deploy sync check` | Deploy-Sync |

## Auf dem S8 (Kali/Termux)

Volles Desktop-VS-Code ist auf 3.6 GB RAM unpraktisch. Optionen:

| Weg | Hinweis |
|-----|---------|
| **PC + Remote/SSH** | Beste UX: VS Code Remote-SSH aufs Gerät / Repo sync |
| **Cursor / VS Code auf PC** | Workspace-Datei öffnen, lokal oder remote |
| **code-server** | Browser-IDE, ~300–500 MB+; nur wenn RAM frei |
| **Acode / Termux** | Leichtgewichtig editieren, ohne volle IDE |

### code-server (optional, speicherhungrig)

```bash
# nur wenn genug RAM/Disk (~1 GB frei empfohlen)
curl -fsSL https://code-server.dev/install.sh | sh
code-server --bind-addr 0.0.0.0:8443 /root/isaacnew
# dann im Handy-Browser: http://<ip>:8443
```

`.vscode/`-Settings greifen dann automatisch.

## Was konfiguriert ist

- Python-Interpreter → `.venv`
- `ISAAC_DISABLE_VECTOR_MEMORY=1` im integrierten Terminal
- Unittest-Discovery: `tests_*.py`
- Schwere Ordner aus Search/Watch ausgeschlossen (`data/`, `logs/`, `mychromadb_env/`, `web/node_modules`)
- Launch: Isaac Core, Unittests, Sanity
- Secrets: `.env` / `data/` bleiben gitignored — nicht committen

## Architektur-Hinweise (Editor)

Kanonische Anweisung: `AGENTS.md`.  
Fokus-Dateien: `isaac_core.py`, `executor.py`, `low_complexity.py`, `memory.py`, `tool_*.py`.

---

*Isaac Kernel · VS Code Workspace*


## code-server auf dem S8 (installiert)

Standalone: `~/.local/bin/code-server` (v4.130.0 arm64).

```bash
# starten
bash scripts/start_code_server.sh
# URL
#   http://127.0.0.1:8443
#   http://<LAN-IP>:8443   # z.B. im gleichen WLAN vom PC/Handy
# Passwort (lokal, gitignored):
cat data/cli_auth_backup/code_server_password.txt
# Log
tail -f logs/code-server.log
```

Config: `~/.config/code-server/config.yaml` (`bind-addr: 0.0.0.0:8443`).

**RAM:** code-server ist speicherhungrig — bei Engpass Isaac stoppen oder nur PC-VS-Code nutzen.
