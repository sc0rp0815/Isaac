# Owner-Befehle (Natural Language Admin)

Referenz für imperative Befehle in natürlicher Sprache. Aktiv nur mit:

```env
ISAAC_PRIVILEGE_MODE=admin
```

Siehe auch: [ANDROID_ADMIN_MODE.md](../ANDROID_ADMIN_MODE.md)

---

## Schnellstart

```bash
# Termux (S8+)
cd ~/Isaac && source .venv/bin/activate
export ISAAC_PRIVILEGE_MODE=admin
python3 scripts/owner_action_live_test.py          # Erkennung + sichere Ausführung
python3 scripts/owner_action_live_test.py --live   # inkl. Termux-API (auf Gerät)
```

Im Isaac-Chat (Dashboard oder CLI) einfach sprechen — z. B. `Isaac, zeige wlan status`.

**Anrede:** `Isaac, suche …` (Komma) funktioniert. `isaac status` bleibt als Systembefehl erhalten.

**Nicht als Befehl:** Erklär-Chat (`erkläre mir das Wetter als Motiv in Literatur`) → normaler Chat-Pfad.

### Owner-Autonomie (Background, bounded)

Proaktive geplante Tasks nur im Admin-Modus (`owner_autonomy.py`):

| Env | Wirkung |
|-----|---------|
| `ISAAC_OWNER_AUTONOMY=0` | aus |
| `ISAAC_OWNER_AUTONOMY_MAX_PER_CYCLE=2` | max. Tasks pro Background-Zyklus (Default 2) |
| `ISAAC_OWNER_AUTONOMY_HEALTH_START/END` | Zeitfenster Health-Task |
| `ISAAC_OWNER_AUTONOMY_NIGHTLY_*` | nächtliches Downloads-Cleanup |

Grenzen: Constitution-Gate vor Ausführung, Failure-Backoff, inspectable Status in `isaac status`.

---

## Kommunikation

| Befehl | Aktion |
|--------|--------|
| `öffne posteingang` / `öffne gmail` | Gmail öffnen |
| `schreib email an max@example.com` | Gmail-Entwurf |
| `suche in mails nach rechnung` | Gmail-Suche |
| `rufe an 01701234567` | Wählfeld (Android) |
| `schick sms an 01709999999` | SMS-App |
| `öffne kontakte` | Kontakte-App |
| `suche kontakt Müller` | Kontakt-Suche |
| `öffne whatsapp` / `telegram` / `discord` | Web-Apps |

---

## Kalender & Zeit

| Befehl | Aktion |
|--------|--------|
| `was steht heute im kalender` | Google Kalender (Tag) |
| `zeige termine diese woche` | Wochenansicht |
| `öffne google kalender` | Kalender |
| `erstelle termin Arzt Donnerstag` | Termin anlegen |
| `wecker um 7:30` | Wecker-App |
| `timer 5 minuten` / `timer 30 sekunden` | Countdown (Termux) |

---

## Medien & Fotos

| Befehl | Aktion |
|--------|--------|
| `Isaac, suche bei Google Fotos raus über gelbe Blumen` | Google-Fotos-Suche |
| `suche in meinen fotos nach gelbe blumen` | Fotos-Suche |
| `öffne google fotos` | Google Fotos |
| `spiele auf spotify Bohemian Rhapsody` | Spotify-Suche |
| `spiele auf youtube Python Tutorial` | YouTube-Suche |
| `öffne netflix` / `twitch` / `ard` / `zdf` | Streaming |
| `mach screenshot` | Screenshot → `workspace/` |
| `fotografiere` / `mach ein foto` | Kamera |

---

## Web, Wetter, Übersetzung

| Befehl | Aktion |
|--------|--------|
| `suche bei google nach asyncio tutorial` | Websuche + Browser |
| `übersetze guten Morgen nach englisch` | Google Translate |
| `zeige wetter in Berlin` | Wetter (imperativ) |
| `wie ist das wetter in Hamburg` | Wetter |
| `öffne wikipedia` / `reddit` / `chatgpt` | Site-Alias |

---

## Navigation & Ort

| Befehl | Aktion |
|--------|--------|
| `navigiere nach Berlin Hauptbahnhof` | Google Maps Route |
| `route nach München` | Navigation |
| `wo bin ich` | GPS (Termux: `termux-location`) |

---

## Netzwerk & WLAN

| Befehl | Aktion |
|--------|--------|
| `zeig mir den wlan status` | WLAN-Status + Gateway |
| `scanne wlan netzwerke` | WLAN-Scan |
| `verbinde dich mit wlan "MeinHeim"` | WLAN verbinden |
| `öffne wlan einstellungen` | WLAN-Settings |
| `öffne die router oberfläche` | Router-UI (`http://gateway`) |
| `schalte wlan aus` / `schalte wlan an` | WLAN-Toggle |
| `ping google.com` | Ping |
| `speedtest` | Geschwindigkeitstest |

Optional in `.env`:

```env
ISAAC_WIFI_SSID=MeinHeim
ISAAC_WIFI_PASSWORD=geheim
```

---

## Bluetooth & Geräte-Toggles

| Befehl | Aktion |
|--------|--------|
| `öffne bluetooth` | Bluetooth-Einstellungen |
| `scanne bluetooth geräte` | BT-Scan (Termux) |
| `schalte taschenlampe an` / `aus` | Torch |
| `schalte flugmodus an` | Flugmodus-Settings |
| `hotspot an` | Tethering-Settings |
| `mobile daten an` | Mobilfunk-Settings |

---

## Gerätestatus

| Befehl | Aktion |
|--------|--------|
| `zeige akku status` | Batterie |
| `wie voll ist mein speicher` | `df -h` |
| `zeige meine ip` | Netzwerkadressen |
| `wie spät ist es` | Datum/Uhrzeit |
| `zeige prozesse` | CPU/RAM-Auslastung |

---

## Dateien & Aufräumen

| Befehl | Aktion |
|--------|--------|
| `zeige dateien in ~/Downloads` | Verzeichnis listen |
| `kopiere ~/a.txt nach ~/b.txt` | Kopieren |
| `verschiebe … nach …` | Verschieben |
| `lösche datei ~/tmp/old.txt` | Datei löschen |
| `lies datei ~/.bashrc` | Datei lesen |
| `schreibe in datei ~/x.txt inhalt: Hallo` | Datei schreiben |
| `erstelle ordner ~/neu` | Ordner anlegen |
| `finde datei config.py in ~/workspace` | Dateisuche |
| `komprimiere ~/ordner nach ~/ordner.zip` | Zip |
| `entpacke ~/archiv.zip` | Unzip |
| `öffne ordner ~/Downloads` | Dateimanager |
| `räume mein dateisystem auf` | System-Cleanup |
| `räume downloads auf` | Cleanup nur Downloads |
| `zeig mir was du beim dateisystem aufräumen würdest` | Dry-Run |
| `lade herunter https://example.com/file.zip` | curl-Download |

---

## Shopping

| Befehl | Aktion |
|--------|--------|
| `suche auf amazon nach usb c kabel` | Amazon |
| `suche auf ebay nach laptop` | eBay |
| `öffne kleinanzeigen` | Kleinanzeigen |

---

## Sprache, Clipboard, Benachrichtigungen

| Befehl | Aktion |
|--------|--------|
| `lies vor: Isaac ist bereit` | TTS (Termux) |
| `lies zwischenablage` | Clipboard lesen |
| `kopiere in die zwischenablage Hallo` | Clipboard setzen |
| `benachrichtige mich Backup fertig` | Notification |

---

## Isaac & Entwicklung

| Befehl | Aktion |
|--------|--------|
| `isaac status` | Kernel-Status |
| `isaac logs` | Log-Tail |
| `git status` / `git pull` | Git im Repo |
| `installiere paket curl` | apt/pkg/pip |
| `führe aus: ls -la` | Shell |

---

## Site-Aliase (Auswahl)

`gmail`, `google kalender`, `google fotos`, `youtube`, `spotify`, `whatsapp`, `github`, `maps`, `wikipedia`, `chatgpt`, `deepl`, `netflix`, `reddit`, `instagram`, `outlook`, `dropbox`, `paypal`, `news`, `keep`, `docs`, `sheets`, `twitch`, `ard`, `zdf`, `booking`

Öffnen mit: `öffne …`, `starte …`, `navigiere zu …`

---

## Android-Einstellungen (Intent)

`einstellungen`, `wlan`, `bluetooth`, `speicher`, `akku`, `display`, `lautstärke`, `benachrichtigungen`, `standort`, `nfc`, `vpn`, `usb`, `hotspot`, `entwickleroptionen`, `datenschutz`, `sicherheit`, `rechner`, `uhr`, `qr` / `barcode scanner`

---

## S8+ — dieses Gerät (Linux-Root auf USERDATA)

Dieses Samsung S8 läuft **nicht** in Termux, sondern mit **nativem Linux-Root**
auf der USERDATA-Partition (`/dev/block/.../USERDATA`). Erkennbar an:

- `wlan0` + `rmnet*` Netzinterfaces
- Repo unter `/root/isaacnew`
- Kein `/data/data/com.termux`

Gerätespezifische Einstellungen in `.env.local` (gitignored):

```env
ISAAC_PRIVILEGE_MODE=admin
ISAAC_RUNTIME_ENV=s8
ISAAC_OWNER=Steffen
```

WLAN-Status nutzt `iwgetid` / `ip` statt Termux-API oder NetworkManager.

---

## S8+ Live-Test (Termux-Variante)

### 1. Repo aktualisieren

```bash
cd ~/Isaac
git pull
source .venv/bin/activate
pip install -q -r requirements.txt
```

### 2. Admin-Modus prüfen

```bash
grep ISAAC_PRIVILEGE_MODE .env
# Erwartung: ISAAC_PRIVILEGE_MODE=admin
```

### 3. Live-Test-Suite

```bash
cd ~/Isaac
ISAAC_DISABLE_VECTOR_MEMORY=1 python3 scripts/owner_action_live_test.py
ISAAC_DISABLE_VECTOR_MEMORY=1 python3 scripts/owner_action_live_test.py --live
```

### 4. Isaac-Kernel (End-to-End)

```bash
# Terminal 1
bash run_isaac.sh

# Terminal 2 — einzelne Befehle
python3 - <<'PY'
import asyncio, os
os.environ["ISAAC_PRIVILEGE_MODE"] = "admin"
from isaac_core import IsaacKernel
async def main():
    k = IsaacKernel()
    for cmd in [
        "zeige wlan status",
        "isaac status",
        "räume downloads auf",
    ]:
        print(">>>", cmd)
        print(await k.process(cmd))
        print()
asyncio.run(main())
PY
```

### 5. Remote Hub (iPhone / Tailscale)

```bash
# Auf dem S8
bash ~/s8_remote/install_termux.sh   # einmalig
s8-hub-start

# Test-Agent
bash ~/Isaac/s8_remote/agents/owner-action-test.sh
```

Von iPhone (Tailscale-IP des S8):

```text
http://S8_TAILSCALE_IP:8768/agents/owner-action-test?token=DEIN_TOKEN
```

Siehe [s8_remote/IPHONE_SHORTCUTS.md](../s8_remote/IPHONE_SHORTCUTS.md).

---

## Termux-API (empfohlen auf S8)

```bash
pkg install termux-api
# Termux:API App aus F-Droid installieren
```

Benötigt für: WLAN-Scan, Akku, Standort, TTS, Clipboard, Torch, Notifications, Screenshots.

---

## Grenzen (ehrlich)

| Thema | Limit |
|-------|--------|
| WLAN Auto-Join | Oft nur gespeicherte Netze; Isaac öffnet Settings |
| Google Fotos / Gmail | Login im Browser nötig |
| Admin-Modus | Nur lokal/trusted device |
| `user`-Modus | Kein Owner-Action-Routing (Validierung A–G unverändert) |

---

*Isaac Owner-Action Routing — `owner_action.py`*