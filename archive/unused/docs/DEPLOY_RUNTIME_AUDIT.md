# Isaac Deploy Runtime Audit

**Kanonischer Start:** `python3 isaac_core.py`  
**Wrapper:** `sh run_isaac.sh`

## Kritische Startfallen
- isaac_core.py: Dashboard-Port ist auf 8766 hart verdrahtet und ignoriert DASHBOARD_PORT aus .env.
- isaac_core.py: Banner zeigt WebSocket-Port 8765 hart verdrahtet an, auch wenn MONITOR_PORT anders gesetzt ist.
- .env.example bewirbt OpenRouter, aber config.py definiert keinen openrouter-Provider.
- browser.py importiert Playwright direkt, aber requirements.txt markiert playwright nur als optional/auskommentiert.
- vector_memory.py nutzt ChromaDB zur Laufzeit, aber requirements.txt markiert chromadb nur als optional/auskommentiert.
- web_urldispatcher.py ist im aktuellen Paket isoliert und verweist auf fehlende interne Module; nicht als Startmodul verwenden.
- tool_runtime.py verwendet requests synchron innerhalb async run_tool(); das kann den Event-Loop blockieren.
- monitor_server.py greift auf die interne Methode executor._notify() zu; das ist funktional, aber eng gekoppelt und fragil bei Refactors.

## Harte Checkliste bei Startfehlern
- 1. Im Zielordner zuerst: python3 sanity_check.py
- 2. Wenn Flask fehlt: python3 -m pip install -r requirements.txt
- 3. Wenn playwright fehlt: python3 -m pip install playwright && python3 -m playwright install chromium
- 4. Wenn chromadb fehlt und Memory-Import scheitert: python3 -m pip install chromadb
- 5. .env prüfen: ACTIVE_PROVIDER, OLLAMA_HOST, OLLAMA_MODEL, MONITOR_PORT, DASHBOARD_PORT, API-Keys.
- 6. Bei ACTIVE_PROVIDER=ollama sicherstellen, dass Ollama wirklich läuft und das Modell existiert.
- 7. Wenn Dashboard nicht erreichbar ist, prüfen ob localhost-Bindung im jeweiligen Umfeld erreichbar ist.
- 8. Wenn Ports belegt sind, aktuell auch den Code prüfen, weil isaac_core.py das Dashboard auf 8766 fest setzt.
- 9. web_urldispatcher.py nicht als produktive Komponente betrachten; im aktuellen Paket ist es ein Artefakt.
- 10. Bei Browser-/Login-Fehlern prüfen: browser_creds.json, Playwright-Installation, Headless-Modus, Site-Selektoren.

## Hinweise
- `playwright` und `chromadb` sind im aktuellen Code faktisch nicht rein optional, solange die Imports global erfolgen.
- `OpenRouter` ist in `.env.example` erwähnt, aber im Konfigurationsstand dieses Pakets nicht als Provider aktiviert.
- `web_urldispatcher.py` sollte im jetzigen Paket nicht als produktives Modul behandelt werden.