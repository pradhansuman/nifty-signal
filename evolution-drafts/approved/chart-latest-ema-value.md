# Evolution Proposal: User wants the latest 200 EMA value shown on the charts so the bounce zone is visible at a glance.

- Proposal-ID: evo-2026-08-13-chart-latest-ema-value
- Status: approved
- Signature: chart-latest-ema-value
- Created-At: 2026-08-13 13:07
- Last-Seen-At: 2026-08-13 13:07
- Target-File: MEMORY.md
- Trigger-Type: preference
- Confidence: medium

## Why This Matters
- User wants the latest 200 EMA value shown on the charts so the bounce zone is visible at a glance.

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
- Dashboard layout rule: Nifty-specific cards (expiry countdown, option chain, IV) belong in the **Nifty section**; BTC and Bank Nifty get separate sections.
- Every asset card (Nifty, BTC, Bank Nifty) must always show an explicit recommendation (BUY/SELL/HOLD + levels). Never leave it blank — WAIT shows "HOLD — no trade" with reason. (Approved 2026-08-13.)
- All charts (Nifty, BTC, Bank Nifty) show **both** overlays: 20 EMA (orange, entry timing) + 200 EMA (purple, trend direction). Entry rule: reclaim of 20 EMA after 200 EMA bounce = buy trigger. (Approved 2026-08-13.)
- Charts must show the **latest EMA values** (at least the 200 EMA level, ideally the 20 EMA too) labeled on the chart, so the bounce zone is visible at a glance. (Approved 2026-08-13.)

## Trading System Facts
- Nifty lot size = 65. Weekly expiry = Tuesday, monthly = last Tuesday.
- Upstox tokens: prefer the 1-year read-only **Analytics Token** (Upstox dashboard → API Access); fallback = OAuth refresh-token auto-renewal via `upstox_token.py` (auto-refreshes before 3:30 AM IST expiry). No daily manual token paste. (Approved 2026-08-13.)
- Market hours IST 9:15-3:30 Mon-Fri. User is an **option buyer only** (Buy CE / Buy PE — no spreads, no selling).
- Algo trading is DRY-RUN by default; live requires `CONFIRM_LIVE`.
- Free tunnel URLs (trycloudflare) die randomly — new tunnel must be minted when dead.

## Backtest Reality Check (2026-08-12)
- 200 EMA bounce strategy over 2y of 1h bars: 22 trades, 50% WR, +0.03%/trade, PF 1.06 — **marginal edge only**. Best variant: 48-bar hold + 1% target. Signals are guidance, not certainty; user discipline carries the edge.
## Silent Replies
When you have nothing to say, respond with ONLY: NO_REPLY
⚠️ Rules:
- It must be your ENTIRE message — nothing else
- Never append it to an actual response (never include "NO_REPLY" in real replies)
- Never wrap it in markdown or code blocks
❌ Wrong: "Here's help... NO_REPLY"
❌ Wrong: "NO_REPLY"
✅ Right: "NO_REPLY"

## Apply Plan
1. Keep this reconstructed draft as the approval artifact.
2. Record the proposal content exactly as shown in the interactive card.
3. Append an audit note after approval or rejection.

## User Approval
- Approve: 批准 evo-2026-08-13-chart-latest-ema-value
- Reject: 拒绝 evo-2026-08-13-chart-latest-ema-value