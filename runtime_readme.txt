Isaac Hybrid Runtime Bundle

Enthalten:
- tool_registry.py
- secrets_store.py
- browser_chat.py
- tool_runtime.py
- dashboard_api.py
- installer_dashboard.html

Was dieses Bundle abdeckt:
- API-Tools
- Browser-Chat-Tools
- Suchmaschinen-Tools
- lokales Script-Tool
- einfacher Installations-Wizard im Dashboard
- Tool-Auswahl per Prompt-Kategorie
- Trust/Ranking pro Tool

Was noch projektabhängig integriert werden muss:
- Einhängen von dashboard_api in deine Flask- oder aiohttp-App
- Verbindung mit executor.py / isaac_core.py
- Browser-Chat-Selektoren im jeweiligen browser_chat-Tool hinterlegen
- Optional: bestehendes Mission-Control-Dashboard um Installer-Modal erweitern

Beispiel Browser-Chat-Metadata:
{
  "input_selector": "textarea",
  "submit_selector": "button[type=submit]",
  "answer_selector": ".message"
}

Hinweis:
Dieses Bundle ist absichtlich modular gehalten, damit es in dein vorhandenes
System mit isaac_core.py, executor.py, relay.py und dashboard.html eingebaut
werden kann, statt es zu ersetzen.
