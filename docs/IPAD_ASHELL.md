# Isaac auf iPad (a-Shell) + S8 Termux/NetHunter

Zielbild (Hybrid): **iPad Air M3 = Konsole / Rechen-Workflow**, **S8 = Gerätekörper**, **Render = immer erreichbarer Chat**, **Cognee = gemeinsames Memory**.

Zielbild (**alles iPad**, inkl. lokales LLM): siehe [Lokales LLM / „Ollama“ auf dem iPad](#lokales-llm--ollama-auf-dem-ipad).

## Was realistisch ist

| Auf dem iPad (a-Shell / Safari) | Besser auf S8 | Besser Render / Cloud |
|--------------------------------|---------------|------------------------|
| Safari → Isaac Free Chat | Termux-API (Akku, GPS, …) | 24/7 erreichbarer Endpoint |
| Optional: Kernel **im Vordergrund** | NetHunter / Netzwerk-Tools | LLM-APIs (Groq, OpenRouter, …) |
| Git, Python-Skripte, `gh` (wenn lauffähig) | Längerer Background / wake-lock | Copilot Cloud Agent Tasks |
| Grok **Web/App** als schwerer Agent | Owner-Filesystem am Phone | Sentry |
| **Lokales LLM** via iOS-Server-App (Ollama-API / OpenAI-Compat) | Ollama in Termux oft zu langsam/RAM-eng | — |

**Nicht erwarten:** offizielles Ollama-Binary in a-Shell, 24/7-Daemon nur unter iOS, NetHunter auf iPad, 70B-Modelle.

---

## Stufe A — Sofort (kein Kernel auf dem iPad)

1. Safari öffnen: https://isaac-free.onrender.com  
2. Chat testen: `Hallo Isaac`, `status:pipeline`  
3. Gleiche Cognee-Keys wie lokal (Memory geteilt)  
4. S8 weiter für Gerätestatus / Owner-Ops  

Fertig: du nutzt die **M3-UI**, Rechenlast der Modelle bleibt bei den **Cloud-APIs**.

---

## Stufe B — Isaac-Kernel in a-Shell (Smoke)

Nur wenn Python 3.10+ und `pip` in a-Shell verfügbar sind.

### 1. Repo

```bash
# Beispiel — Pfade je nach a-Shell anpassen
cd ~
git clone https://github.com/sc0rp0815/Isaac.git isaacnew   # preferred; legacy: sco0rp/IsaacNew
cd isaacnew
git checkout main
git pull
```

### 2. Slim-Deps (Free-Profil)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements-free.txt
# falls requirements-free fehlt: aiohttp websockets python-dotenv sentry-sdk …
```

### 3. Env (niemals in Screenshots posten)

```bash
cat > ~/.isaac.env << 'EOF'
ACTIVE_PROVIDER=openrouter
OPENROUTER_API_KEY=
# oder GROQ_API_KEY= / GOOGLE_API_KEY=
ISAAC_DISABLE_VECTOR_MEMORY=1
ISAAC_BIND_HOST=127.0.0.1
MONITOR_HTTP_PORT=8766
MONITOR_PORT=8765
ISAAC_COGNEE_ENABLED=1
ISAAC_COGNEE_ALLOW_CLOUD=1
COGNEE_BASE_URL=
COGNEE_API_KEY=
ISAAC_EXTERNAL_MEMORY_WRITE=1
SENTRY_DSN=
EOF
chmod 600 ~/.isaac.env
set -a; source ~/.isaac.env; set +a
```

### 4. Start

```bash
cd ~/isaacnew
source .venv/bin/activate
set -a; source ~/.isaac.env; set +a
python3 isaac_core.py
```

Safari (auf dem iPad): http://127.0.0.1:8766  

### 5. Smoke

- `Hallo Isaac` → lokale Antwort  
- `status:pipeline` → Render/Cognee/Sentry-Zeilen  
- App wechseln → Prozess kann sterben → **normal unter iOS**

---

## Lokales LLM / „Ollama“ auf dem iPad

### Harte Grenze

| | |
|--|--|
| Offizielles **Ollama** (ollama.com) auf iPadOS | **Nein** — kein iPad-Build; Metal/MLX-Ollama = **macOS** |
| Ollama-Binary in **a-Shell** | **Praktisch nein** |
| **Lokale** Inferenz auf M3 | **Ja** — über **iOS-Apps** mit lokalem HTTP-Server |
| Isaac anbinden | **Ja** — Provider `ollama` oder `local` → `127.0.0.1` |

„Ollama auf dem iPad“ = **App mit Ollama-kompatibler oder OpenAI-kompatibler API**, die das M3 nutzt — nicht `curl | sh` von ollama.com.

S8 ist für schwere lokale Modelle oft zu schwach; der **Air M3** ist die bessere On-Device-Inferenz-Plattform **über eine LLM-Server-App**, nicht über Termux-Ollama.

### Zielbild „alles iPad“

```text
[iOS Local-LLM-App :11434 oder :PORT]
         ▲
         │ HTTP localhost
[Isaac in a-Shell] ──► Safari http://127.0.0.1:8766
[Grok Web/App]         (schwere Agenten-Dialoge)
```

Beide Apps (LLM-Server + a-Shell) müssen **aktiv** sein; iOS beendet Background-Prozesse.

### S0 — Local-Server-App wählen und testen

1. App installieren, die **lokal** serviert (Beispiele im Ökosystem: Apps mit „Ollama-style API“ / Local LLM Server; GGUF-Apps mit API — **selbst prüfen**, Port und API-Typ in der App-Doku).
2. Kleines Modell laden (z. B. 1B–3B quantisiert).
3. In a-Shell erreichbarkeit testen:

```bash
# Ollama-API?
curl -s http://127.0.0.1:11434/api/tags
# oder OpenAI-Compat?
curl -s http://127.0.0.1:PORT/v1/models
```

Notiere: **Port**, **API-Typ** (Ollama vs OpenAI), **Model-Name**.

### S1 — Isaac auf Local-App zeigen

Env-Vorlage im Repo: [`deploy/ipad/isaac-ipad-local.env.example`](../deploy/ipad/isaac-ipad-local.env.example)

**A) App spricht Ollama-API (`/api/chat`, `/api/tags`):**

```bash
ACTIVE_PROVIDER=ollama
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=phi3:mini          # exakter Name aus der App /api/tags
ISAAC_DISABLE_VECTOR_MEMORY=1
ISAAC_BIND_HOST=127.0.0.1
```

**B) App spricht OpenAI Chat Completions:**

```bash
ACTIVE_PROVIDER=local
LOCAL_LLM_ENABLED=1
ISAAC_ALLOW_LOCAL_LLM=1
LOCAL_LLM_BASE_URL=http://127.0.0.1:PORT/v1/chat/completions
LOCAL_LLM_MODEL=mein-modell     # exakt wie /v1/models
LOCAL_LLM_TIMEOUT=300
ISAAC_DISABLE_VECTOR_MEMORY=1
ISAAC_BIND_HOST=127.0.0.1
```

Start wie Stufe B; dann:

1. Local-LLM-App starten + Modell laden  
2. a-Shell: Isaac starten  
3. Safari: Dashboard  
4. `Hallo Isaac` (lokal, kein LLM)  
5. `Was ist 2+2?` (soll über local/ollama laufen)  
6. `status:pipeline` → Zeile **Local LLM** / Ollama erreichbar  

Siehe auch [LOCAL_LLM.md](LOCAL_LLM.md).

### Modellgröße (Richtwert Air M3)

| RAM-Klasse | Sinnvoller Start |
|------------|------------------|
| 8 GB | 1B–3B Q4 |
| 12 GB+ | 3B–7B Q4, vors |

Bei OOM: kleineres Modell / stärkere Quantisierung.

### S8 und Ollama

- **LLM:** iPad (App), nicht S8  
- **S8:** optional nur Device/NetHunter, oder aus LLM-Pfaden streichen  
- Termux-Ollama auf S8 nur als Notlösung  

---

## Stufe C — Agenten „wie Grok“

| Weg | Empfehlung |
|-----|------------|
| Schwere Dialoge / Planung | **Grok Web oder App** auf dem iPad |
| Lokale / private Inferenz | Local-LLM-App + Isaac (oben) |
| Isaac + Tools auf Render | Safari → Render (Fallback wenn iPad-Session tot) |
| Repo-PRs | GitHub im Browser oder CCA (Cloud Agent), nicht NetHunter |
| Optional CLI in a-Shell | nur wenn `node`/`grok`/`gh` installierbar und stabil |

Isaac-Companion-Flags (`ISAAC_GROK_AGENT_ENABLED=1` …) nur, wenn der Kernel in a-Shell stabil läuft **und** das Binary im PATH ist.

---

## Stufe D — S8 vom iPad aus erreichen

1. **Tailscale** auf iPad + S8 (gleicher Account)  
2. S8: Isaac + optional `s8_remote` Hub (`install_termux.sh`)  
3. iPad Safari: `http://<tailscale-ip-s8>:8766` (Dashboard) oder Hub-Port  
4. Shortcuts analog `s8_remote/IPHONE_SHORTCUTS.md`  

So bleibt die **Rechen-/Chat-Arbeit am iPad**, die **Geräte-Hände am S8**.

---

## Rollen-Cheat-Sheet

```text
iPad M3     → denken, schreiben, Agents (UI + Cloud-APIs)
S8 NH       → fühlen, tun, NetHunter, Termux-API
Render      → immer erreichbarer Isaac-Chat
Cognee      → gemeinsames Gedächtnis
Sentry      → Fehler
```

---

## Troubleshooting a-Shell

| Problem | Idee |
|---------|------|
| `pip` / wheels fail | slim `requirements-free`, kein onnx/chroma |
| Port belegt | andere `MONITOR_HTTP_PORT` |
| Kein Netz zu Render | a-Shell Netzwerk-Rechte / VPN |
| Prozess weg nach App-Wechsel | akzeptieren oder Render als Always-on nutzen |
| Zu wenig Speicher | kein Vector-Memory, ein Provider |

---

## Siehe auch

- [ISAAC_REMOTE.md](ISAAC_REMOTE.md) — `cloud:` / `both:` Fleet  
- [FREE_HOSTING.md](FREE_HOSTING.md) — Render Free  
- [LOCAL_LLM.md](LOCAL_LLM.md) — Provider `local` / Ollama  
- [OWNER_COMMANDS.md](OWNER_COMMANDS.md) — Termux/S8  
- [AUTOMATION_PIPELINE.md](AUTOMATION_PIPELINE.md) — `status:pipeline`  
- [COPILOT_AGENT.md](COPILOT_AGENT.md) / [GROK_AGENT.md](GROK_AGENT.md) — Companions  
- Env-Beispiel: [`deploy/ipad/isaac-ipad-local.env.example`](../deploy/ipad/isaac-ipad-local.env.example)  

