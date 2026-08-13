# NSE Option Chain — Google Apps Script Bridge

## Why this exists
NSE's API (`nseindia.com/api/option-chain-indices`) is geo-blocked — requests from non-Indian IPs return 403/404. Google's servers run from Indian IPs and are NOT blocked. This bridge runs on Google's infrastructure and returns clean JSON.

## Deployment (takes ~3 minutes, one-time)

### Step 1: Open Google Apps Script
1. Go to https://script.google.com
2. Click **"New project"**
3. Delete any default code in the editor

### Step 2: Paste the script
1. Open [nse_fetcher.gs](/nse_fetcher.gs) from this workspace
2. Copy the entire contents
3. Paste into the Apps Script editor
4. Click the save icon (or Ctrl+S)

### Step 3: Deploy as Web App
1. Click **"Deploy"** (top-right blue button) → **"New deployment"**
2. Click the gear ⚙️ icon → Select **"Web app"**
3. Configure:
   - **Description:** `NSE Option Chain Fetcher`
   - **Execute as:** `Me` (your Google account)
   - **Who has access:** `Anyone` (the data is public NSE data)
4. Click **"Deploy"**
5. **Authorize** when prompted (this allows the script to make HTTP requests)
6. **Copy the Web App URL** — it looks like:
   `https://script.google.com/macros/s/AKfycb.../exec`

### Step 4: Test it
Visit the URL in your browser with query params:
```
https://script.google.com/macros/s/.../exec?symbol=NIFTY&expiry=27-Aug-2026
```
You should see a JSON response with `"success": true` and chain data.

### Step 5: Wire it to the pipeline
```
python nifty_pipeline_v2.py --nse-proxy "https://script.google.com/macros/s/YOUR_ID/exec"
```

That's it. Every run will now auto-fetch live NSE option chain data.

## Optional: List available expiries
```
https://script.google.com/macros/s/.../exec?symbol=NIFTY&format=expiries
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Script not deployed" / 404 | Re-deploy: Deploy → Manage deployments → Edit → New version |
| "Authorization required" | You skipped the OAuth screen — re-deploy and authorize |
| Empty chain / 0 strikes | Check the expiry date format: `DD-Mon-YYYY` (e.g. `27-Aug-2026`) |
| Timeout | First run is slow (cold start). Subsequent runs are faster. Increase Python timeout if needed. |

---

## Render Cloud Deployment (Telegram alerts from the cloud)

The app is Render-ready: `Dockerfile` + `render.yaml` blueprint. Cloud mode boots with the **alert scheduler, Telegram batcher, and cache warmup enabled by default** (macOS instance should be stopped to avoid duplicate pushes).

### Deploy (one-time, ~5 min)
1. **Push** this repo to GitHub (already done — `pradhansuman/nifty-signal`).
2. Render dashboard → **New → Blueprint** → pick the repo (or New Web Service → Docker → root).
3. Render auto-detects `render.yaml` / `Dockerfile`.
4. Set env vars in the Render dashboard (never commit these):
   - `TELEGRAM_BOT_TOKEN` — bot token from @BotFather
   - `TELEGRAM_CHAT_ID` — your chat id (already known: 5094931498)
   - `UPSTOX_ANALYTICS_TOKEN` — 1-year Upstox analytics token
   - `NO_SCHEDULER=false` — keep the scheduler ON (default)
5. Deploy. Health check hits `/` → 200.

### Verified end-to-end (2026-08-13)
- Cloud-mode boot: scheduler + Telegram + warmup threads start; `/api/signal` 200.
- **Env-var-only Telegram path tested**: a real push was delivered using only `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` (no config file) — exactly the Render scenario.
- Static pages `/` and `/v2` serve; chart API works.

### ⚠️ Caveats
- **Free tier sleeps** after ~15 min idle → scheduler pauses with it. Keep it awake with a free uptime pinger (UptimeRobot, 5-min interval) hitting `/`.
- **Run alerts from ONE host** — Mac + Render together = every alert twice (both schedulers fire). Either stop the Mac instance, or set `NO_SCHEDULER=true` on one of them.
- `.openclaw/tmp/*.py` secrets are git-ignored → NOT in the image; env vars are the only credential source on Render.
- Disk caches (backtest, OI snapshots, alerts) are ephemeral on Render — they rebuild per boot; fine.
