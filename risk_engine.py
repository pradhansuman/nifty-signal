#!/usr/bin/env python3
"""
Risk Engine — day-level trade limits + position sizing for the scalper.

Enforces the "don't dig deeper" rules the framework demands:
  1. Max ₹ loss per day      → stop trading once hit
  2. Max trades per day      → stop overtrading
  3. Consecutive-loss stop   → step away after N straight losers
  4. Position sizing         → risk a fixed % of capital per trade

Pure functions — no network, fully testable. Config is overridable.
"""
from __future__ import annotations

DEFAULTS = {
    "max_loss_rs_day": 10000.0,   # ₹ stop for the day
    "max_trades_day": 10,         # max resolved trades/day
    "max_consecutive_losses": 3,  # stop after N straight losers
    "capital": 100000.0,          # ₹ account size (sizing base)
    "risk_pct": 1.0,              # % of capital risked per trade
}


def _pnl(t):
    """₹ pnl for a resolved trade; falls back to pts (spot assets) when ₹ absent."""
    rs = t.get("pnl_rs")
    if rs is not None and rs != 0:
        return float(rs)
    return float(t.get("pnl_pts") or 0.0)


def check_limits(resolved_trades, config=None):
    """Return {ok, blocks, details} for today's resolved trades.

    resolved_trades: list of dicts with pnl_rs/pnl_pts (resolved scalp calls).
    blocks: list of breached-limit keys (empty => ok).
    """
    cfg = {**DEFAULTS, **(config or {})}
    blocks = []
    trades = list(resolved_trades or [])

    net = sum(_pnl(t) for t in trades)
    n = len(trades)

    # consecutive losses (count back from the most recent)
    consec = 0
    for t in reversed(trades):
        if _pnl(t) < 0:
            consec += 1
        else:
            break

    if net <= -cfg["max_loss_rs_day"]:
        blocks.append("max_loss_day")
    if n >= cfg["max_trades_day"]:
        blocks.append("max_trades_day")
    if consec >= cfg["max_consecutive_losses"]:
        blocks.append("consecutive_losses")

    return {
        "ok": not blocks,
        "blocks": blocks,
        "details": {
            "net_rs": round(net, 2),
            "trades": n,
            "consecutive_losses": consec,
            "max_loss_rs_day": cfg["max_loss_rs_day"],
            "max_trades_day": cfg["max_trades_day"],
            "max_consecutive_losses": cfg["max_consecutive_losses"],
            "remaining_loss_rs": round(cfg["max_loss_rs_day"] + net, 2) if net < 0 else cfg["max_loss_rs_day"],
            "remaining_trades": max(0, cfg["max_trades_day"] - n),
        },
    }


def position_size(capital, risk_pct, stop_distance, lot_size=None):
    """Max ₹ risk budget per trade, and max lots given a stop distance.

    stop_distance: |entry - stop| in ₹ (premium terms) — the per-unit risk.
    """
    budget = capital * risk_pct / 100.0
    if stop_distance <= 0:
        return {"budget_rs": round(budget, 2), "units": 0, "lots": 0}
    units = budget / stop_distance
    lots = int(units // lot_size) if lot_size else 0
    return {"budget_rs": round(budget, 2), "units": int(units), "lots": lots}


if __name__ == "__main__":
    import json
    # demo: 4 trades today, -6,000 net, 2 straight losses
    trades = [
        {"pnl_rs": -3000.0}, {"pnl_rs": -2000.0}, {"pnl_rs": -1000.0}, {"pnl_rs": 0.0},
    ]
    print(json.dumps(check_limits(trades), indent=2))
    print(json.dumps(position_size(100000, 1.0, 12.0, 65), indent=2))
