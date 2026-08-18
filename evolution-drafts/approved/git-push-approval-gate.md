# Evolution Proposal: Record the git workflow gate: before pushing to git, show the user the changes and their impact and wait for an explicit yes, so future pushes never go out unapproved.

- Proposal-ID: evo-2026-08-15-git-push-approval-gate
- Status: approved
- Signature: git-push-approval-gate
- Created-At: 2026-08-15 17:53
- Last-Seen-At: 2026-08-15 17:53
- Target-File: MEMORY.md
- Trigger-Type: preference
- Confidence: medium

## Why This Matters
- Record the git workflow gate: before pushing to git, show the user the changes and their impact and wait for an explicit yes, so future pushes never go out unapproved.

## Evidence
- Interactive proposal card was present in the session UI.
- The original pending draft file was unavailable at approval time.
- AutoClaw reconstructed this draft from the proposal payload so the review result can still be recorded.

## Duplicate Check
- Checked: pending draft path + signature/proposal fallback
- Result: original draft file missing
- Decision: create surrogate draft from proposal payload

## Proposed Change
### MEMORY.md

# MEMORY.md — Long-Term Memory

## Trading Dashboard Preferences
- User's options analysis dashboard section priority: **IV Rank first** (directly improves entry timing as a buyer), then **Backtesting** (confirms the edge), then the **Chain table**.
- User is building market prediction/trading tools covering Indian equities (Nifty, BTST strategy) and Bitcoin, with features added as separate sections.
- Feature build priority (approved 2026-08-12): **Telegram push alerts** → **Nifty chart with 200 EMA overlay** → **smarter backtest**. Telegram awaits user messaging the bot for chat-id discovery.
- Dashboard layout rule: Nifty-specific cards (expiry countdown, option chain, IV) belong in the **Nifty section**; BTC, Bank Nifty, and Sensex get separate sections. (Sensex section approved 2026-08-13.)
- The ⚡ **NIFTY SCALPER** section sits at the **top** of the dashboard (right after Live alerts), above the Nifty strategy card and everything else. (Approved 2026-08-14.)
- The option chain on the dashboard main page is **Nifty's** (always visible, NOT collapsed). (Approved 2026-08-14.)
- The **Bank Nifty** option chain lives in the **Advanced cards** section, and the **Position Sizing** and **Stop Loss** cards are removed from the dashboard. (Approved 2026-08-14.)
- Every asset card (Nifty, BTC, Bank Nifty, Sensex) must always show an explicit recommendation (BUY/SELL/HOLD + levels). Never leave it blank — WAIT shows "HOLD — no trade" with reason. (Approved 2026-08-13.)
- All charts (Nifty, BTC, Bank Nifty, Sensex) show **both** overlays: 20 EMA (orange, entry timing) + 200 EMA (purple, trend direction). Entry rule: reclaim of 20 EMA after 200 EMA bounce = buy trigger. (Approved 2026-08-13.)
- Charts must show the **latest EMA values** (at least the 200 EMA level, ideally the 20 EMA too) labeled on the chart, so the bounce zone is visible at a glance. (Approved 2026-08-13.)
- Alerts: only buy/sell signal alerts are wanted — no other alert types should fire. (Approved 2026-08-14.)
- Locale/language: dashboard UI locale should be **Odia (Oriya)**. (Approved 2026-08-14.)
- Telegram alerts: all Telegram alert messages should be in **Odia (Oriya)**. (Approved 2026-08-14.)

## Trading System Facts
- Nifty lot size = 65. Weekly expiry = Tuesday, monthly = last Tuesday.
- Upstox tokens: prefer the 1-year read-only **Analytics Token** (Upstox dashboard → API Access); fallback = OAuth refresh-token auto-renewal via `upstox_token.py` (auto-refreshes before 3:30 AM IST expiry). No daily manual token paste. (Approved 2026-08-13.)
- Market hours IST 9:15-3:30 Mon-Fri. User is an **option buyer only** (Buy CE / Buy PE — no spreads, no selling).
- Bitcoin data/broker source = **Delta Exchange** (https://www.delta.exchange — India-licensed crypto derivatives exchange). The BTC arm of the tool runs against Delta Exchange data, parallel to Nifty on Upstox. (Approved 2026-08-14.)
- Algo trading is DRY-RUN by default; live requires `CONFIRM_LIVE`.
- Server + Telegram alerts now run on **Render**: https://nifty-signal-n684.onrender.com (stable URL — no trycloudflare tunnel needed). (Approved 2026-08-13.) **Render AUTO-DEPLOYS on every git push** (2026-08-14: it served latest scalp_pnl/scalp_calls features without a Manual Deploy click, but later that same day scalp features were missing on Render while present locally — auto-deploy only covers what is actually pushed to git).
- **Local vs Render sync check** (2026-08-14): when a feature exists locally but is missing on Render (e.g. scalp P/L + scalp calls), first verify the code was committed AND pushed to git before assuming Render is broken or needs a manual deploy.
- **Git push gate** (approved 2026-08-15): before pushing to git, show the user what is being changed and the impact; only push after the user explicitly says yes.
- Alerting = **Render primary + Mac failover** (approved 2026-08-14): the Mac's tg_sender probes Render /api/health (7s timeout, 45s cache) and pushes only when Render is down or free-tier sleeping — no duplicates when both are up, no missed alerts when Render fails. Both schedulers run; keep the keep-alive LaunchAgent (com.nifty.render-keepalive, 5-min ping) to minimize Render sleep. Render free tier still **sleeps after ~15 min idle**; Mac LaunchAgent plist kept for rollback (`launchctl load ~/Library/LaunchAgents/com.nifty.signal-server.plist`).
- Uptime preference (approved 2026-08-13): the server/dashboard should run **as long as the laptop is working**, and Render should be **always on** in the cloud as the permanent instance (like a cloud service, not a temporary tunnel). Dual-host setup: Mac runs dashboard + scheduler (failover sender via health probe), Render is the primary Telegram sender.

## Backtest Reality Check (2026-08-12)
- 200 EMA bounce strategy over 2y of 1h bars: 22 trades, 50% WR, +0.03%/trade, PF 1.06 — **marginal edge only**. Best variant: 48-bar hold + 1% target. Signals are guidance, not certainty; user discipline carries the edge.

## Unit Tests (2026-08-14)
- Trading code has an offline test suite in `tests/` (mocks yfinance/Upstox/chain — no network needed): scalper scoring + all 5 gates + call-building guards, algo_trader dry-run/limits/instrument keys, server _clean_nan + scalp call lifecycle (once-only target/stop/expired). 34 tests, all passing as of 2026-08-14.
- Run before shipping code changes: `.openclaw/tmp/venv/bin/python3 -m unittest discover -s tests -v`

## Apply Plan
1. Keep this reconstructed draft as the approval artifact.
2. Record the proposal content exactly as shown in the interactive card.
3. Append an audit note after approval or rejection.

## User Approval
- Approve: 批准 evo-2026-08-15-git-push-approval-gate
- Reject: 拒绝 evo-2026-08-15-git-push-approval-gate
## Audit Note (2026-08-15 17:54)
- Applied to MEMORY.md by user approval ("批准 evo-2026-08-15-git-push-approval-gate").
