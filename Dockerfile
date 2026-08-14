# Nifty Signal — Render / NAS Docker Setup
# Works on: Render, Railway, Synology, QNAP, TrueNAS, any Linux NAS with Docker

FROM python:3.12-slim

WORKDIR /app

# Install dependencies from the pinned lockfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full app (all modules + static assets).
# NOTE: .openclaw/tmp/*.py secrets are git-ignored → NOT in the image.
#       On Render, supply them via env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
#       UPSTOX_ANALYTICS_TOKEN (the code falls back to env vars automatically).
COPY *.py ./
COPY pwa_static/ ./pwa_static/
# Runtime tuning knobs (chatty/strict overrides) — committed so cloud matches local.
COPY .openclaw/tmp/scalper_tuning.json ./.openclaw/tmp/scalper_tuning.json

# Render sets PORT automatically; fallback for NAS/docker-compose
ENV PORT=5099

EXPOSE 5099

# Render web service expects the app to bind $PORT — nifty_server reads it from env
CMD ["python", "nifty_server.py"]
