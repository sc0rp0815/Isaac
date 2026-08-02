---
title: Isaac Free
emoji: 🧠
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Isaac Free (Hugging Face Space)

Zero-billing Docker Space for the Isaac kernel (dashboard + chat).

## Secrets (Space Settings → Variables and secrets)

Set **at least one** free LLM key:

| Secret | Provider |
|--------|----------|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) (empfohlen) |
| `GOOGLE_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) free models |

Optional:

```
ACTIVE_PROVIDER=groq
ISAAC_FREE_CLOUD=1
```

## Deploy

1. Create a new **Docker** Space on Hugging Face.
2. Point it at this repo **or** copy **`Dockerfile.free`** (not `Dockerfile`!) as `Dockerfile` in the Space root.
   > ⚠️ **Important:** `Dockerfile` includes heavy dependencies (Playwright/ChromaDB) and will exceed HF Spaces limits.
3. Add secrets above.
4. Open the Space URL — dashboard at `/`, health at `/healthz`, WS at `/ws`.

**Hinweis:** Free Spaces schlafen nach Inaktivität ein. Isaac bleibt lokal-first; Space = optionaler Online-Zugang.
