# Isaac Web App

Eine minimalistische Web-Anwendung für Isaac – lokaler, datenschutzorientierter KI-Kern.

## Features

✅ **Lokale Speicherung** – Konversationen werden im Browser gespeichert (IndexedDB/localStorage)  
✅ **Datenschutz** – Keine Telemetrie, alles lokal  
✅ **Einfache UI** – Clean, minimalistisch, dunkel  
✅ **Offline-ready** – Kann auch ohne Backend starten  
✅ **Backend-Integration** – REST API zu Python-Server  

## Setup

### Option 1: Schnell starten (ohne Backend)

```bash
cd app/
# Einfach index.html im Browser öffnen
# z.B.: python -m http.server 8000
# Dann: http://localhost:8000
```

### Option 2: Mit Python-Backend

1. **Isaac Python-Server starten:**
```bash
python -m isaac.api  # oder dein Startup-Script
# Läuft auf http://localhost:5000
```

2. **Web-App starten:**
```bash
cd app/
python -m http.server 8000
# Öffne: http://localhost:8000
```

## Backend-Integration

Die App erwartet einen `/chat` Endpoint:

```json
POST /chat
{
  "message": "Benutzer-Frage",
  "history": [{"sender": "user", "text": "..."}]
}

Response:
{
  "response": "Isaac Antwort"
}
```

### Beispiel Flask-Integration:

```python
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    message = data['message']
    history = data.get('history', [])
    
    # Isaac Logic hier
    response = isaac.process_message(message, history)
    
    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(port=5000, debug=True)
```

## Tastenkombinationen

- **Enter** – Nachricht senden
- **Shift+Enter** – Neue Zeile (später)
- **Ctrl+Shift+X** – Konversation löschen

## Struktur

```
app/
├── index.html      # HTML Struktur
├── style.css       # Styling (Tailwind-inspired)
├── app.js          # Chat-Logik & Backend-Integration
└── README.md       # Diese Datei
```

## Nächste Schritte

- [ ] WebSocket statt REST für Echtzeit
- [ ] Offline-Mode mit Service Worker
- [ ] Gedächtnis-Visualisierung
- [ ] Benutzer-Profile & Kontexte
- [ ] Export/Import von Konversationen
- [ ] Dark/Light Mode Toggle

## Lizenz

Same as Isaac project
