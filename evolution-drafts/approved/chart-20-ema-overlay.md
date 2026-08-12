# Evolution Proposal: All dashboard charts (Nifty / BTC / Bank Nifty) must include a 20 EMA overlay for entry timing, in addition to the 200 EMA trend line.

- Proposal-ID: evo-2026-08-13-chart-20-ema-overlay
- Status: approved
- Signature: chart-20-ema-overlay
- Created-At: 2026-08-13 00:41
- Last-Seen-At: 2026-08-13 00:41
- Target-File: MEMORY.md
- Trigger-Type: preference
- Confidence: medium

## Why This Matters
- 200 EMA = direction (trend line); 20 EMA = entry timing (fast momentum). Price reclaiming the 20 EMA after a 200 EMA bounce is the entry trigger for the user's option-buying strategy. Every chart card should show both overlays so the user can act on the combo without switching tools.

## Evidence
- Interactive proposal card was present in the session UI.
- Original pending draft file unavailable at approval time; reconstructed from proposal payload.

## Proposed Change
### MEMORY.md — add under "Trading Dashboard Preferences"
- All charts (Nifty, BTC, Bank Nifty) show **both** overlays: 20 EMA (orange, entry timing) + 200 EMA (purple, trend direction). Entry rule: reclaim of 20 EMA after 200 EMA bounce = buy trigger. (Approved 2026-08-13.)

## Apply Plan
1. Keep this reconstructed draft as the approval artifact.
2. Record the proposal content in MEMORY.md.
3. Append audit note after approval.

## User Approval
- Approve: 批准 evo-2026-08-13-chart-20-ema-overlay
