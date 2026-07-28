# Context7 — Library Docs Tool (bounded)

**Rolle:** Expliziter Doku-Lookup für Libraries/Frameworks über die Context7 API.  
**Nicht:** Memory-Backend, zweiter Kernel, opportunistisches Tooling im Normal-Chat.

---

## Flags

| Env | Default | Bedeutung |
|-----|---------|-----------|
| `CONTEXT7_API_KEY` | — | API key (`ctx7sk-…`) |
| `ISAAC_CONTEXT7_ENABLED` | auto `1` wenn Key | Adapter an |
| `CONTEXT7_BASE_URL` | `https://context7.com` | API base |
| `ISAAC_CONTEXT7_TIMEOUT` | `20` | HTTP timeout (s), clamp 3–60 |
| `ISAAC_CONTEXT7_MAX_SNIPPETS` | `6` | max code snippets |

**Niemals** Keys committen. Nur `.env` / Render Secrets / `data/cli_auth_backup/`.

---

## Owner-Befehle (explizit)

```text
docs: fastapi | APIRouter prefix
docs: /vercel/next.js middleware auth
docs: react useState
context7: django queryset
ctx7: /websites/fastapi_tiangolo routing
context7 status
docs status
```

Aliases: `context7:`, `ctx7:`, `doku:`, `library docs:`, `lib docs:`.

### Parse-Regeln

1. `docs: /owner/repo THEMA` → Library-ID direkt  
2. `docs: name | THEMA` oder `name :: THEMA` → Library suchen, dann Context  
3. `docs: name thema…` → erstes Token als Library-Hint, ganzer Text als Query  

---

## Architektur

```
Owner prefix → Intent.CONTEXT7 → Context7Adapter.lookup()
  → GET /api/v2/libs/search  (optional)
  → GET /api/v2/context?type=json
```

- **Kein** Eintrag in `search_all()` / Memory-Retrieval  
- **Kein** automatisches Tool bei Chat über „docs“ in normaler Sprache  
- Privilege: `chat_response` (read-only)

Modul: `external_memory/context7_adapter.py`  
Status: `external memory` / `context7 status`

---

## Smoke

```bash
cd /root/isaacnew
ISAAC_DISABLE_VECTOR_MEMORY=1 .venv/bin/python - <<'PY'
from external_memory import get_external_memory_bridge, reset_external_memory_bridge
reset_external_memory_bridge()
b = get_external_memory_bridge()
print(b.context7.status())
print(b.context7.lookup("fastapi | APIRouter")["ok"])
PY
```

Tests: `python3 -m unittest tests_context7_adapter`

---

*Isaac Kernel v5.3 | bounded Context7 docs tool*
