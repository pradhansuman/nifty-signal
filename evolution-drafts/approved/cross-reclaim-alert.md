# Evolution Proposal: Cross & reclaim alerts (20/50 + 20 EMA)

- Proposal-ID: evo-2026-08-17-cross-reclaim-alert
- Signature: cross-reclaim-alert
- Status: approved
- Created-At: 2026-08-17 14:29
- Target-File: MEMORY.md (Trading Dashboard Preferences)

## Why This Matters
- User wanted alerts not only for the 9/21 EMA cross but also for the
  **20/50 trend-change cross** and the **spot-vs-20-EMA reclaim** (their own
  entry rule: "reclaim of 20 EMA after 200 EMA bounce = buy trigger").

## Rule
- **Cross/reclaim alerts** — three actionable cross alerts exist on Nifty:
  1. 9/21 EMA cross (5m) — intraday momentum flip
  2. 20/50 trend cross (1h) — trend-change golden/death cross
  3. 20 EMA reclaim/loss (15m) — entry-zone reclaim trigger
  All carry Entry / Stop Loss / Target / Exit rule (ATR 1×/2×, 2:1 R:R) and
  fire once per transition (day-level dedup). (Approved 2026-08-17.)

## Apply Plan
1. Add to MEMORY.md after approval.
2. This draft is the audit note.
