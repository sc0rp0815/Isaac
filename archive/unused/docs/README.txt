Isaac Dashboard Tools Patch

Enthalten:
- tool_registry.py
- secrets_store.py
- dashboard_api.py
- dashboard_tools.html
- integration_example.py

Kurz-Einbau:

1) Dateien in dein Projekt kopieren
2) In deiner Flask-App das Blueprint registrieren:
   from dashboard_api import dashboard_api
   app.register_blueprint(dashboard_api)

3) Optional das Dashboard-HTML als eigene Route ausliefern
4) Danach stehen bereit:
   GET  /api/tools
   GET  /api/tools/<tool_id>
   POST /api/tools/add
   POST /api/tools/update
   POST /api/tools/test
   POST /api/tools/toggle
   POST /api/tools/delete
   POST /api/tools/set-priority

Hinweis:
- API-Keys werden lokal in data/secrets_store.json gespeichert
- Für Produktion später verschlüsseln oder in OS-Keychain legen
