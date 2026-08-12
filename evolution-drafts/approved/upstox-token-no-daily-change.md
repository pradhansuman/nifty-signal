# Evolution Proposal: Upstox token handling must not require daily manual paste — use the 1-year Analytics Token (read-only) as primary, with OAuth refresh-token auto-renewal as secondary.

- Proposal-ID: evo-2026-08-13-upstox-token-no-daily-change
- Status: approved
- Signature: upstox-token-no-daily-change
- Created-At: 2026-08-13 00:49
- Last-Seen-At: 2026-08-13 00:49
- Target-File: MEMORY.md
- Trigger-Type: preference
- Confidence: medium

## Why This Matters
- The daily access token chore (re-paste every ~24h) is a recurring operational burden. Upstox offers a 1-year read-only Analytics Token and OAuth refresh tokens; the dashboard should never depend on daily manual input.

## Evidence
- Interactive proposal card was present in the session UI.
- Original pending draft file unavailable at approval time; reconstructed from proposal payload.

## Proposed Change
### MEMORY.md — add under "Trading System Facts"
- Upstox tokens: prefer the 1-year read-only **Analytics Token** (dashboard → API Access); fallback = OAuth refresh-token auto-renewal via `upstox_token.py` (auto-refreshes before 3:30 AM IST expiry). No daily manual token paste. (Approved 2026-08-13.)

## Apply Plan
1. Keep this reconstructed draft as the approval artifact.
2. Record the proposal content in MEMORY.md.
3. Append audit note after approval.

## User Approval
- Approve: 批准 evo-2026-08-13-upstox-token-no-daily-change
