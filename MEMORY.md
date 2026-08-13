# MEMORY.md — Long-Term Memory

## Trading Dashboard Preferences
- User's options analysis dashboard section priority: **IV Rank first** (directly improves entry timing as a buyer), then **Backtesting** (confirms the edge), then the **Chain table**.
- User is building market prediction/trading tools covering Indian equities (Nifty, BTST strategy) and Bitcoin, with features added as separate sections.
- Feature build priority (approved 2026-08-12): **Telegram push alerts** → **Nifty chart with 200 EMA overlay** → **smarter backtest**. Telegram awaits user messaging the bot for chat-id discovery.
- Dashboard layout rule: Nifty-specific cards (expiry countdown, option chain, IV) belong in the **Nifty section**; BTC and Bank Nifty get separate sections.
- Every asset card (Nifty, BTC, Bank Nifty) must always show an explicit recommendation (BUY/SELL/HOLD + levels). Never leave it blank — WAIT shows "HOLD — no trade" with reason. (Approved 2026-08-13.)
- All charts (Nifty, BTC, Bank Nifty) show **both** overlays: 20 EMA (orange, entry timing) + 200 EMA (purple, trend direction). Entry rule: reclaim of 20 EMA after 200 EMA bounce = buy trigger. (Approved 2026-08-13.)

## Trading System Facts
- Nifty lot size = 65. Weekly expiry = Tuesday, monthly = last Tuesday.
- Upstox tokens: prefer the 1-year read-only **Analytics Token** (Upstox dashboard → API Access); fallback = OAuth refresh-token auto-renewal via `upstox_token.py` (auto-refreshes before 3:30 AM IST expiry). No daily manual token paste. (Approved 2026-08-13.)
- Market hours IST 9:15-3:30 Mon-Fri. User is an **option buyer only** (Buy CE / Buy PE — no spreads, no selling).
- Algo trading is DRY-RUN by default; live requires `CONFIRM_LIVE`.
- Free tunnel URLs (trycloudflare) die randomly — new tunnel must be minted when dead.

## Backtest Reality Check (2026-08-12)
- 200 EMA bounce strategy over 2y of 1h bars: 22 trades, 50% WR, +0.03%/trade, PF 1.06 — **marginal edge only**. Best variant: 48-bar hold + 1% target. Signals are guidance, not certainty; user discipline carries the edge.
