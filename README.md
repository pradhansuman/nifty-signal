# Nifty 50 Options Trading System

A complete **research → signal → size → execute → journal** pipeline for Nifty 50 options trading. Built around the 200 EMA bounce setup with live Upstox OI/PCR/IV data, real delta-based position sizing, multi-strategy signals, paper/dry-run trading, and a mobile PWA dashboard.

---

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐
│  Yahoo Fin  │    │  Upstox API  │    │  Upstox API   │
│  (spot/VIX) │    │  (OI/PCR/IV) │    │  (orders)     │
└──────┬──────┘    └──────┬───────┘    └───────┬───────┘
       │                  │                     │
       ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────┐
│                  nifty_monitor.py                   │
│  - 200 EMA bounce (ADX, RSI, DI+/-)                │
│  - Enrichment: real delta, premiums, OI, VIX       │
│  - BTST, trailing stop, PCR contrarian             │
└──────────────────────┬──────────────────────────────┘
                       │ JSON
┌──────────────────────▼──────────────────────────────┐
│                 nifty_server.py (Flask)              │
│  - REST API (/api/signal, /api/intraday, etc.)      │
│  - Background alert scheduler (all strategies)      │
│  - Paper P&L auto-tracking                          │
│  - Serves PWA dashboard                             │
└──────┬───────────────────────────────────┬──────────┘
       │                                   │
       ▼                                   ▼
┌──────────────┐               ┌─────────────────────┐
│  PWA Dashboard│               │  Cloudflare Tunnel   │
│  (mobile)     │               │  → public HTTPS URL  │
└──────────────┘               └─────────────────────┘
```

---

## Setup

### Prerequisites

- Python 3.9+
- Upstox developer account with API access token
- Mac (LaunchAgent auto-start) or any machine

### 1. Clone & install

```bash
git clone https://github.com/pradhansuman/nifty-signal.git
cd nifty-signal
python3 -m venv .openclaw/tmp/venv
source .openclaw/tmp/venv/bin/activate
pip install -r requirements.txt
```

### 2. Add Upstox token

```bash
echo 'UPSTOX_ACCESS_TOKEN = "your-jwt-token-here"' > .openclaw/tmp/upstox_config.py
```

On cloud (Render/Railway): set `UPSTOX_TOKEN` environment variable instead.

### 3. Start the server

```bash
python nifty_server.py
```

Dashboard at `http://localhost:5099`.

### 4. Expose publicly (optional)

```bash
# Cloudflare tunnel (free HTTPS)
cloudflared tunnel --url http://localhost:5099
```

### 5. Auto-start on Mac (optional)

```bash
cp .openclaw/tmp/com.nifty.signal-server.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.nifty.signal-server.plist
```

---

## File Map

| File | Purpose |
|---|---|
| `nifty_server.py` | Flask API server + background alert scheduler + PWA host |
| `nifty_monitor.py` | Primary signal engine — 200 EMA, ADX, BTST, PCR contrarian |
| `intraday_signals.py` | VWAP reversion + 9/21 EMA crossover on 5-min bars |
| `orb_scalp.py` | Opening Range Breakout scalp (9:30-10:15 AM) |
| `nifty_pipeline_v2.py` | Full 15-step analysis (spot, regime, scenarios, IV) |
| `premarket_brief.py` | Pre-market overview script |
| `algo_trader.py` | Trade execution, paper P&L, strategy toggles, daily limits |
| `trade_journal.py` | Manual trade logging + P&L stats |
| `upstox_fetch.py` | Standalone Upstox option chain fetcher |
| `pwa_static/index.html` | Mobile PWA dashboard — all features |
| `pwa_static/sw.js` | Service worker (offline support, network-first) |
| `pwa_static/manifest.json` | PWA install manifest |
| `requirements.txt` | Python dependencies |
| `.openclaw/tmp/upstox_config.py` | **Your Upstox token** (git-ignored, never committed) |
| `.openclaw/tmp/algo_config.json` | Algo trading config (max lots, loss limits) |
| `Dockerfile` / `docker-compose.yml` | Docker + NAS deployment |

---

## Strategies

### 1. 200 EMA Bounce (Primary)
Fires when Nifty touches 200 EMA with ADX > 18, DI+ > DI-, and bullish EMA stack. Delivers Bull Call Spread or Bear Put Spread recommendations with stop loss and 1σ expected move.

### 2. PCR Reversal (Contrarian)
Fires when OI PCR drops below 0.7 (euphoria → sell calls) or rises above 1.4 (panic → sell puts). Mean-reversion overlay on the trend-following primary.

### 3. Opening Range Breakout (ORB)
Records 9:15-9:30 range. Fires on breakout above > BUY CE, breakdown below > BUY PE. Active 9:30-10:15 AM only.

### 4. VWAP Reversion
Price > 0.5% above VWAP → SELL. Price > 0.5% below VWAP → BUY. Active all day.

### 5. 9/21 EMA Crossover
Golden cross (9 EMA > 21 EMA) → BUY. Death cross → SELL. Active all day.

---

## Daily Trading Checklist

| Time | Action |
|---|---|
| **9:00 AM** | Check Pre-Market Brief alert (spot, VIX, PCR, levels) |
| **9:15 AM** | Market opens — 200 EMA monitor starts |
| **9:30 AM** | ORB window opens — watch for breakout |
| **9:30-3:30 PM** | VWAP + EMA signals update every 5 min |
| **Every 15 min** | 200 EMA signal + PCR contrarian check |
| **3:25 PM** | BTST close-out reminder |
| **3:30 PM** | Market closes |

---

## Algo Trading (DRY RUN by default)

All strategies default to **dry-run** — orders are logged, nothing is placed.

**To enable a strategy:**
```bash
curl -X POST http://localhost:5099/api/algo/strategy \
  -H 'Content-Type: application/json' \
  -d '{"strategy":"ema_bounce","enable":true}'
```

**To switch to LIVE trading** (⚠️ real money):
```bash
curl -X POST http://localhost:5099/api/algo/toggle \
  -H 'Content-Type: application/json' \
  -d '{"enable":true,"confirm":"CONFIRM_LIVE"}'
```

Safety rails: max 2 lots/trade, 10 lots/day, ₹10,000 daily loss limit auto-pauses.

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/signal` | Current 200 EMA signal with OI, PCR, IV, premiums |
| `GET /api/intraday` | VWAP + EMA crossover signals |
| `GET /api/orb` | ORB breakout signal |
| `GET /api/full` | Full 15-step pipeline |
| `GET /api/summary` | Lightweight summary |
| `GET /api/position-size?capital=X&risk_pct=Y` | Position sizing with real delta |
| `GET/POST /api/journal` | Trade journal CRUD |
| `GET /api/alerts` | Recent background alerts |
| `GET /api/algo/status` | Algo state, positions, paper P&L |
| `POST /api/algo/toggle` | Enable/disable live mode |
| `POST /api/algo/strategy` | Toggle individual strategies |
| `GET /api/tunnel` | Cloudflare tunnel URL |
| `GET /api/health` | Health check |

---

## Configuration

| Config File | What |
|---|---|
| `.openclaw/tmp/upstox_config.py` | Upstox access token |
| `.openclaw/tmp/algo_config.json` | Algo params (lots, loss limit, strategies) |
| `~/Library/LaunchAgents/com.nifty.signal-server.plist` | Auto-start on Mac reboot |
| Environment variable `UPSTOX_TOKEN` | Cloud deployment token |
| Environment variable `PORT` | Server port (default 5099) |
| Environment variable `RENDER=true` | Cloud mode flag |

---

## Deployment

### Local (Mac)
```bash
python nifty_server.py
# + cloudflared tunnel for public access
```

### Render (free cloud)
1. Connect repo to Render
2. Start command: `gunicorn nifty_server:app --bind 0.0.0.0:$PORT --timeout 90`
3. Env vars: `UPSTOX_TOKEN`, `RENDER=true`, `PYTHONUNBUFFERED=1`

### Docker / NAS
```bash
docker build -t nifty-signal .
docker run -p 5099:5099 -e UPSTOX_TOKEN=*** nifty-signal
```

---

## Notes

- Nifty lot size is 65 (hardcoded — change in `algo_trader.py`, `nifty_server.py`, `trade_journal.py`, and `pwa_static/index.html` if NSE revises)
- Upstox JWT tokens expire in ~24h — refresh and paste into config
- Cloudflare tunnel URL changes on tunnel restart — saved to `.openclaw/tmp/tunnel_url.txt`
- All sensitive data (token, journal, alerts, orders) is git-ignored — never committed

---

## License

MIT
