# Isaac Local Development Image (mit Playwright/ChromaDB für lokale Tests)
# Für Free-Cloud: Dockerfile.free verwenden!
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ISAAC_FREE_CLOUD=0 \
    ISAAC_BIND_HOST=localhost \
    PORT=8766

WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# App source (avoid shipping local .venv / secrets)
COPY *.py ./
COPY dashboard.html ./
COPY docs ./docs
COPY scripts ./scripts

# data dir created at runtime (empty SQLite)
RUN mkdir -p data logs workspace

EXPOSE 8766

# Health: GET /healthz
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,urllib.request; p=os.environ.get('PORT','8766'); urllib.request.urlopen(f'http://127.0.0.1:{p}/healthz', timeout=3)"

CMD ["python", "isaac_core.py"]
