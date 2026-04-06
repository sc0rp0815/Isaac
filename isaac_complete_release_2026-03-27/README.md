# Isaac v5.0 – Mission Control

## Schnellstart

```bash
# 1. Dependencies
pip install aiohttp websockets python-dotenv

# 2. Konfiguration
cp .env.example .env
nano .env    # Keys eintragen

# 3. Starten
python isaac_core.py
```

Browser öffnen: **http://localhost:8766**

---

## Architektur

```
isaac/
├── config.py          Einzige Wahrheitsquelle für alle Einstellungen
├── privilege.py       STEFFEN > ISAAC > TASK > GUEST
├── memory.py          SQLite: Konversationen, Fakten, Direktiven
├── audit.py           Append-Only Log (Isaac kann es nicht löschen)
├── logic.py           Qualitätsbewertung + autonome Nachfragen
├── relay.py           Async Multi-Provider (10 Provider)
├── executor.py        Task-Engine mit Isolation und Qualitätskontrolle
├── monitor_server.py  WebSocket-Server für Dashboard
├── isaac_core.py      Haupt-Orchestrator
└── dashboard.html     Task-Manager Dashboard
```

---

## Privilege-System

```
STEFFEN (100) — Alle Rechte, kann Isaac pausieren
  ISAAC  (70)  — Autonome Entscheidungen, Dateisystem, Internet
    TASK (40)  — Isolierte Aufgabe, sieht nur sich selbst
    GUEST(10)  — Nur lesen
```

Steffen-Input hat immer Vorrang. Direktiven sind permanent.

---

## Befehle

| Eingabe | Aktion |
|---------|--------|
| `direktive: TEXT` | Permanente Anweisung setzen |
| `korrektur: Feld = Wert` | Fakt ins Gedächtnis schreiben |
| `suche: QUERY` | Direkte Internet-Recherche |
| `code: BESCHREIBUNG` | Python-Code generieren |
| `abbrechen ID` | Task abbrechen |
| `pause` / `weiter` | Isaac steuern |
| `status` | System-Bericht |

---

## Logic-Modul

Jede KI-Antwort wird auf 4 Dimensionen bewertet (0–10):

- **Länge** — Genug Inhalt?
- **Abdeckung** — Alle Schlüsselthemen angesprochen?
- **Spezifität** — Konkret oder vage?
- **Kohärenz** — Logisch strukturiert?

Bei Score unter Schwellwert → Isaac generiert automatisch eine gezielte Nachfrage. Max. 3 Iterationen. Bei sehr schlechter Antwort → Provider-Wechsel.

---

## Sicherheit

- **Kein einziger API-Key im Code** — nur `.env`
- `.env` niemals in Git committen
- Audit-Log ist append-only — unveränderlich
- Isaac kann seinen eigenen Audit-Log nicht löschen
- Alle kritischen Aktionen brauchen R-Trace (Begründung)
