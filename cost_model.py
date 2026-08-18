#!/usr/bin/env python3
"""
Cost Model — realistic round-trip execution costs for Indian F&O option buying.

Models the FULL cost of a scalp round trip (buy CE/PE, sell it back), so paper
P&L and backtests reflect reality instead of a zero-cost fantasy.

Rates are the post-2024-Budget Indian F&O charges (configurable — brokers vary).
For a pure OPTION BUYER:
  - Brokerage:  flat ₹20/order (Upstox; other discount brokers same ballpark)
  - STT:        0.1% of premium, SELL side (raised from 0.0625% in Oct-2024 budget)
  - Exchange:   ~0.0495% of premium, both sides (NSE options)
  - SEBI:       ₹10 per ₹1 crore turnover (negligible — ignored below)
  - Stamp duty: 0.003% of premium, buy side
  - GST:        18% on (brokerage + exchange charges)

Why this matters for scalping: on a ₹100-premium Nifty lot (65 units = ₹6,500),
flat brokerage + STT + charges ≈ ₹55–65 per round trip — roughly 0.8–1% of lot
value. That is the single biggest silent killer of a thin scalp edge.
"""
from __future__ import annotations

# ── Configurable constants (₹ / rates) ──────────────────────────────
BROKERAGE_PER_ORDER = 20.0    # ₹ flat per order (buy + sell = 2 orders)
STT_OPTIONS = 0.001           # 0.1% of premium, sell side
EXCHANGE_TXN = 0.000495       # ~0.0495% of premium, each side (NSE)
STAMP_DUTY = 0.00003          # 0.003% of premium, buy side
GST = 0.18                    # 18% on (brokerage + exchange charges)


def round_trip_cost(entry_premium, exit_premium, lot_size, qty=1):
    """Total ₹ cost of a buy→sell round trip for `qty` lots of one option.

    entry_premium / exit_premium: per-unit premium (₹).
    lot_size: units per lot (Nifty 65, BNF 15).
    """
    buy_val = entry_premium * lot_size * qty
    sell_val = exit_premium * lot_size * qty
    brokerage = BROKERAGE_PER_ORDER * 2 * qty
    stt = STT_OPTIONS * sell_val
    txn = EXCHANGE_TXN * (buy_val + sell_val)
    stamp = STAMP_DUTY * buy_val
    gst = GST * (brokerage + txn)
    return brokerage + stt + txn + stamp + gst


def cost_per_unit(entry_premium, exit_premium, lot_size, qty=1):
    """Round-trip cost expressed per unit (₹), so it subtracts from premium pnl."""
    return round_trip_cost(entry_premium, exit_premium, lot_size, qty) / (lot_size * qty)


def cost_pct(entry_premium, exit_premium, lot_size):
    """Round-trip cost as % of the ENTRY lot value (the edge you must clear)."""
    val = entry_premium * lot_size
    if val <= 0:
        return 0.0
    return round_trip_cost(entry_premium, exit_premium, lot_size) / val * 100.0


def breakeven_move(entry_premium, exit_premium, lot_size, half_spread=0.0):
    """Minimum premium appreciation (₹) needed to break even after spread + costs.

    half_spread: half the bid-ask spread in ₹ (buy at ask, sell at bid → you lose
    ~2×half_spread per unit round trip).
    """
    spread_cost = 2.0 * half_spread
    return spread_cost + cost_per_unit(entry_premium, exit_premium, lot_size)


if __name__ == "__main__":
    # Example: ATM Nifty CE, premium ₹120, 1 lot (65)
    for prem in (60, 120, 200):
        cost = round_trip_cost(prem, prem, 65)
        print(f"premium ₹{prem:>3}  lot ₹{prem*65:>6,}  round-trip cost ₹{cost:6.2f}  "
              f"({cost/(prem*65)*100:.2f}%)  breakeven +{breakeven_move(prem, prem, 65, 1.5):.2f}pts")
