# Nifty Signal — Options & Crypto Trading Dashboard

A self-hosted **research → signal → alert → paper-trade → journal** engine for Indian
options and Bitcoin. Covers **Nifty 50**, **Bank Nifty**, **Sensex**, and **Bitcoin**
with a mobile PWA dashboard and **Telegram push alerts**.

Built around the **200 EMA bounce** setup, layered with a **5-min momentum scalper**,
**EMA cross / reclaim alerts**, **stock movers screening**, IV Rank, PCR/OI, FII/DII,
expiry/gamma, and a weekly review. Everything runs in **dry-run (paper) mode by
default** — no real orders are ever placed unless you explicitly enable live trading.

> ⚠️ **This is a research/analysis tool, not financial advice.** Signals are guidance.
> Options trading can lose money fast — trade only what you can afford to lose.

---

## Features

- **4 assets** — Nifty 50, Bank Nifty, Sensex (equity options) + Bitcoin (Delta Exchange perps)
- **200 EMA bounce** primary signal with ADX / DI+/DI− / RSI trend confirmation
- **Nifty Scalper** — 5-min momentum, actionable Buy CE / Buy PE calls (entry, stop, target, expiry)
- **Cross / reclaim alerts** — 9/21 EMA (5m), 20/50 trend cross (1h), 20 EMA reclaim (15m), all with entry / stop / target / exit
- **Stock movers** — NIFTY-50 day-trade & swing screener with ATR targets
- **Option chain** — live Upstox chain, PCR, ATM IV, max pain, IV Rank
- **Telegram alerts** — actionable signals + daily digest, English or Odia
- **Paper P&L** — dry-run trade ledger with daily snapshots
- **Mobile PWA** — installable dashboard, auto-refresh, alert sound

---

## Quick Start

### 1. Prerequisites
- **Python 3.10+**
- An **Upstox developer account** (for the option chain / OI / IV data — free)
- A **Telegram bot** (optional, for alerts)

### 2. Clone & install

```bash
git clone https://github.com/pradhansuman/nifty-signal.git
cd nifty-signal
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure (see [Configuration](#configuration))

### 4. Run

```bash
python nifty_server.py
```

Open the dashboard at **http://localhost:5099** (or `/v2`).

### 5. Run the test suite (optional, no network needed)

```bash
python -m unittest discover -s tests
```

---

## Configuration

All secrets live in **git-ignored** files under `.openclaw/tmp/` (or env vars on cloud).
Create the `tmp` folder if it doesn't exist.

### Upstox (option chain, OI, PCR, IV)

Upstox API is **read-only** for the analytics token — no orders, no risk.

```bash
mkdir -p .openclaw/tmp
cat > .openclaw/tmp/upstox_config.py << 'EOF'
# Preferred: 1-year READ-ONLY Analytics token (Upstox dashboard → API Access)
UPSTOX_ANALYTICS_TOKEN = "your-analytics-token-here"
EOF
```

Token priority: `UPSTOX_ANALYTICS_TOKEN` (1-year read-only) → `UPSTOX_REFRESH_TOKEN`
(auto-refresh OAuth) → `UPSTOX_ACCESS_TOKEN` (manual daily paste).

### Telegram (alerts — optional)

1. Create a bot with [@BotFather](https://t.me/BotFather) → copy the token.
2. Message your bot once, or add it to a group → get the chat id.
   - **Group ids are negative** (e.g. `-5394161679`). Missing the minus → "chat not found".

```bash
cat > .openclaw/tmp/telegram_config.py << 'EOF'
TELEGRAM_BOT_TOKEN = "123456:ABC-your-token"
TELEGRAM_CHAT_ID = "-5394161679"
EOF
```

Alert language (optional): set `TG_LANG=en` for English alerts (default is Odia).

### Bitcoin (Delta Exchange — no keys required)

BTC data comes from Delta Exchange's public REST API (perp mark price + funding).
No account or API key needed — it just works.

---

## Environment Variables (cloud / override)

| Variable | Purpose |
|---|---|
| `PORT` | Server port (default `5099`) |
| `RENDER` | Cloud mode flag (`true`) |
| `NO_SCHEDULER` | `true` = dashboard-only, no background alerts |
| `UPSTOX_TOKEN` | Upstox token for monitor/chain/algo modules |
| `UPSTOX_ANALYTICS_TOKEN` | Upstox analytics token (read by token manager) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat/group id |
| `TG_LANG` | Alert language — `en` (English) or `or` (Odia) |

---

## Deployment

### Local (Mac / Linux) — always-on
```bash
python nifty_server.py
```

### Mac auto-start (LaunchAgent)
```bash
cp .openclaw/tmp/com.nifty.signal-server.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.nifty.signal-server.plist
```

### Render (free cloud — recommended)
`render.yaml` is a full blueprint: connect the repo in Render → **New Blueprint** →
fill in the env vars. It runs the Dockerfile (`python nifty_server.py`), which starts
the scheduler + Telegram sender automatically.

Env vars to set: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `UPSTOX_ANALYTICS_TOKEN`,
`TG_LANG=en`.

> **Note:** the free tier sleeps after ~15 min idle. Keep it warm with a 5-min ping
> (a Mac LaunchAgent or an external cron service such as cron-job.org).

### Docker
```bash
docker build -t nifty-signal .
docker run -p 5099:5099 \
  -e TELEGRAM_BOT_TOKEN=... -e TELEGRAM_CHAT_ID=... \
  -e UPSTOX_ANALYTICS_TOKEN=... nifty-signal
```

> **Vercel is NOT supported** — this app needs a long-running process (background
> scheduler + persistent disk + slow data fetches), which serverless functions can't
> provide. Use Render, Railway, Fly.io, or a VPS instead.

---

## Architecture

```
Yahoo Finance ──┐
Upstox API ─────┼──► Signal engines ──► nifty_server.py (Flask)
Delta Exchange ─┘        │                   │
MrChartist (FII/DII) ────┘                   ├─► REST API (/api/*)
                                             ├─► Background alert scheduler
                                             ├─► Telegram sender (batched)
                                             ├─► Paper P&L tracking
                                             └─► PWA dashboard (pwa_static/)
```

---

## Strategies & Signals

| Strategy | Timeframe | What it does |
|---|---|---|
| **200 EMA bounce** (primary) | 15m / 1h | Long at 200 EMA reclaim with ADX + DI+ confirmation; short on breakdown |
| **Nifty Scalper** | 5m | Momentum score (EMA stack, VWAP, RSI, Stoch) → actionable Buy CE / Buy PE |
| **9/21 EMA cross** | 5m | Golden/death cross momentum flip, with entry/stop/target |
| **20/50 trend cross** | 1h | Trend-change golden/death cross |
| **20 EMA reclaim** | 15m | Spot recapturing the 20 EMA (entry-zone trigger) |
| **ORB** | 9:30–10:15 | Opening-range breakout |
| **VWAP reversion** | 5m | Mean-reversion when price >0.5% from VWAP |
| **PCR contrarian** | 15m | OI PCR <0.7 → sell calls; >1.4 → sell puts |
| **BTST** | EOD | Buy-today-sell-tomorrow carry signal |
| **Stock movers** | daily | NIFTY-50 day-trade (>1.2% + 1.4×vol) + swing screeners |
| **BTC swing** | 1h | 200 EMA + funding-rate gated, 24/7 |

---

## File Map

| File | Purpose |
|---|---|
| `nifty_server.py` | Flask API + background alert scheduler + PWA host |
| `nifty_monitor.py` | Primary 200 EMA signal engine |
| `scalper.py` | 5-min momentum scalper (Nifty/BNF/Sensex/BTC) |
| `intraday_signals.py` | VWAP + EMA cross (9/21, 20/50, 20 EMA reclaim) |
| `btc_monitor.py` | Bitcoin signal engine (Delta Exchange) |
| `banknifty_monitor.py` | Bank Nifty signal engine |
| `sensex_monitor.py` | Sensex signal engine |
| `stock_movers.py` | NIFTY-50 day-trade + swing screener |
| `delta_exchange.py` | Delta Exchange public REST client (no keys) |
| `telegram_alert.py` | Telegram sender (batched, Odia/English) |
| `upstox_fetch.py` / `upstox_token.py` | Upstox chain fetch + token manager |
| `chain_table.py` / `iv_rank.py` / `oi_buildup.py` | Option chain, IV Rank, OI analysis |
| `fii_dii.py` | FII/DII data (MrChartist) |
| `expiry_countdown.py` / `gap_go.py` | Expiry + gap analysis |
| `orb_scalp.py` | Opening-range breakout |
| `nifty_pipeline_v2.py` | Full 15-step analysis |
| `premarket_brief.py` | Pre-market overview (9:00 AM) |
| `tomorrow_outlook.py` / `weekly_review.py` | Next-day + weekly review |
| `algo_trader.py` | Trade execution, paper P&L, strategy toggles |
| `trade_journal.py` | Manual trade logging |
| `backtest.py` / `scalper_backtest.py` / `scalper_filter_backtest.py` / `stock_movers_backtest.py` | Offline backtests |
| `pwa_static/` | PWA dashboard (index.html, dash.js, manifest, service worker) |
| `tests/` | Offline unit tests (no network needed) |
| `requirements.txt` | Python dependencies |
| `Dockerfile` / `docker-compose.yml` / `render.yaml` | Deploy configs |

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/signal` | Nifty 200 EMA signal + OI/PCR/IV/premiums |
| `GET /api/intraday` | VWAP + EMA cross/reclaim signals |
| `GET /api/scalper` | Nifty scalper signal + scalp calls + P&L |
| `GET /api/scalp/history` | Today's scalp call log |
| `GET /api/btc` · `/api/banknifty` · `/api/sensex` | Per-asset signals |
| `GET /api/stocks/movers` | NIFTY-50 movers (day-trade + swing) |
| `GET /api/chain` · `/api/bnf/chain` | Option chains |
| `GET /api/ivrank` · `/api/bnf/ivrank` | IV Rank |
| `GET /api/fiidii` | FII/DII flows |
| `GET /api/expiry` | Expiry countdown |
| `GET /api/weeklyreview` | Weekly review |
| `GET /api/outlook` | Tomorrow outlook |
| `GET /api/chart` | Chart data (EMA overlays) |
| `GET /api/alerts` | Recent background alerts |
| `GET /api/algo/status` | Algo state + paper P&L |
| `GET /api/health` | Health check |
| `POST /api/algo/toggle` · `/api/algo/strategy` | Algo controls |
| `GET/POST /api/journal` | Trade journal |

---

## Daily Trading Checklist

| Time (IST) | Action |
|---|---|
| **9:00 AM** | Pre-market brief (gap, VIX, levels) |
| **9:15 AM** | Market open — monitors start |
| **9:30–10:15 AM** | ORB window |
| **9:15–3:30 PM** | VWAP + EMA cross/reclaim updates every 5 min |
| **Every 15 min** | 200 EMA + PCR contrarian check |
| **3:25 PM** | BTST close-out reminder |
| **3:40 PM** | Daily report (Telegram) |

---

## Safety

- **Dry-run by default** — orders are logged, never placed.
- **Live mode** requires an explicit `CONFIRM_LIVE` confirmation.
- Read-only Upstox Analytics token = no order capability.
- Safety rails: max lots per trade/day, daily loss limit auto-pauses.

---

## Notes

- Nifty lot size = 65 (hardcoded — update if NSE revises).
- Weekly expiry = Tuesday, monthly = last Tuesday.
- Upstox analytics token is valid ~1 year (read-only) — no daily paste needed.
- All sensitive data (tokens, journal, alerts, orders) is git-ignored — never committed.
- Dashboard + Telegram alerts are **English** by default when `TG_LANG=en`.

---

## License

MIT
