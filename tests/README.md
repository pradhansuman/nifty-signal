# Unit tests — Nifty Signal trading system

Run:  `.openclaw/tmp/venv/bin/python3 -m unittest discover -s tests -v`

## Coverage
- **test_scalper.py** (14) — momentum scoring (long/short/flat on synthetic 5m
  data), all gates: trend (SCALP_TREND_MIN), ADX, VIX low/high, window;
  build_call: spread guard >3%, theta guard >2%/day, spread-aware
  target/stop (net of ask/bid), delta 0.40-0.80 filter, tightest-spread pick.
- **test_algo_trader.py** (10) — dry-run order (qty 65, MARKET, log written),
  disabled-strategy block, daily loss limit, max lots/day, max lots/trade,
  unknown strategy, instrument key via chain + compound fallback.
- **test_server_logic.py** (10) — `_clean_nan` (incl. nested), scalp call
  lifecycle: TARGET_HIT/STOP_HIT/EXPIRED fire exactly once, ACTIVE untouched,
  no-premium skip, 20-call cap, `_chain_premium` strike resolution.

All tests are offline: yfinance/Upstox/chain calls are mocked; config + order
logs are isolated to temp dirs.
