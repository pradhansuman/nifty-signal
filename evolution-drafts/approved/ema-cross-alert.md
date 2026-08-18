# Evolution Proposal: Signal alerts must be actionable (EMA cross)

- Proposal-ID: evo-2026-08-17-ema-cross-alert
- Signature: ema-cross-alert
- Status: approved
- Created-At: 2026-08-17 14:17
- Target-File: MEMORY.md (Trading Dashboard Preferences)

## Why This Matters
- User: "when ema cross over happened there is not alert… you should tell when to
  entry, when to exit, price, stop loss, detailed."
- A bare "EMA_BUY" text is not tradeable. Every signal alert must carry entry,
  stop loss, target, and exit rule so it can be acted on directly.

## Rule
- **Signal alerts must be actionable** — always include: Entry (price), Stop Loss,
  Target, and Exit rule. Use ATR(14)-scaled stops (1×ATR) and targets (2×ATR = 2:1
  R:R), mirror direction for SELL. (Approved 2026-08-17.)

## Apply Plan
1. Add to MEMORY.md after approval.
2. This draft is the audit note.
