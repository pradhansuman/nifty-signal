# Evolution Proposal: Signal analysis pipeline (Trade Gate)

- Proposal-ID: evo-2026-08-18-signal-analysis-pipeline
- Signature: signal-analysis-pipeline
- Status: approved
- Created-At: 2026-08-18 10:49
- Target-File: MEMORY.md (Trading Dashboard Preferences)

## Why This Matters
- User supplied a 20-step decision framework for trade decisions (market data →
  data quality → regime → time of day → price action → momentum/volume → VWAP/ORB →
  options filter → liquidity → expected value → risk → execution cost → TRADE/NO
  TRADE → execution → result → MFE/MAE/R → performance → regime analysis →
  continuous testing).

## Rule
- **Trade Gate (signal analysis pipeline)** — every trade decision runs a 12-step
  pre-trade checklist in order and returns TRADE / NO TRADE with a per-step
  PASS/FAIL/WARN breakdown. Hard gates (data, regime, time-of-day, momentum)
  block; liquidity/EV/cost are warn placeholders. Shown on the 🚦 Trade Gate
  dashboard card via `/api/trade-gate`. (Approved 2026-08-18.)
- **MFE / MAE / R tracking is the remaining gap** — max-favorable/max-adverse
  excursion + R-multiple logging on closed trades not yet implemented.

## Apply Plan
1. Add to MEMORY.md after approval.
2. This draft is the audit note.
