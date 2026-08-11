#!/usr/bin/env python3
"""
Trade Journal — Simple JSON-based P&L tracker for Nifty trades.
Used by nifty_server.py. Stores trades in .openclaw/tmp/trade_journal.json
"""

import json, os
from datetime import datetime

JOURNAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "trade_journal.json")

def _load():
    if os.path.exists(JOURNAL_PATH):
        with open(JOURNAL_PATH, "r") as f:
            return json.load(f)
    return {"trades": [], "stats": {}}

def _save(data):
    os.makedirs(os.path.dirname(JOURNAL_PATH), exist_ok=True)
    with open(JOURNAL_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)

def add_trade(trade):
    """Add a trade. Fields: signal, direction, entry_price, exit_price, lots, strike, expiry, notes (exit_price optional for open trades)."""
    data = _load()
    trade["id"] = len(data["trades"]) + 1
    trade["date"] = trade.get("date") or datetime.now().strftime("%Y-%m-%d")
    trade["time"] = trade.get("time") or datetime.now().strftime("%H:%M:%S")
    
    # Calculate P&L if both entry and exit are present
    if trade.get("entry_price") and trade.get("exit_price") and trade.get("lots"):
        entry = trade["entry_price"]
        exit_p = trade["exit_price"]
        lots = trade["lots"]
        lot_size = 65
        if trade.get("direction") == "short":
            trade["pnl"] = round((entry - exit_p) * lots * lot_size, 2)
            trade["pnl_pct"] = round(((entry - exit_p) / entry) * 100, 2)
        else:
            trade["pnl"] = round((exit_p - entry) * lots * lot_size, 2)
            trade["pnl_pct"] = round(((exit_p - entry) / entry) * 100, 2)
        trade["status"] = "closed"
    else:
        trade["pnl"] = None
        trade["status"] = "open"
    
    data["trades"].append(trade)
    _recalc_stats(data)
    _save(data)
    return trade

def update_trade(trade_id, updates):
    """Update an existing trade (e.g., add exit_price to close)."""
    data = _load()
    for t in data["trades"]:
        if t["id"] == trade_id:
            t.update(updates)
            if t.get("entry_price") and t.get("exit_price") and t.get("lots"):
                entry = t["entry_price"]
                exit_p = t["exit_price"]
                lots = t["lots"]
                if t.get("direction") == "short":
                    t["pnl"] = round((entry - exit_p) * lots * 65, 2)
                    t["pnl_pct"] = round(((entry - exit_p) / entry) * 100, 2)
                else:
                    t["pnl"] = round((exit_p - entry) * lots * 65, 2)
                    t["pnl_pct"] = round(((exit_p - entry) / entry) * 100, 2)
                t["status"] = "closed"
            _recalc_stats(data)
            _save(data)
            return t
    return None

def get_all():
    return _load()

def _recalc_stats(data):
    trades = data["trades"]
    closed = [t for t in trades if t.get("status") == "closed" and t.get("pnl") is not None]
    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    
    total_pnl = sum(t["pnl"] for t in closed)
    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0
    avg_win = round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0
    avg_loss = round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0
    rr_ratio = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else None
    max_win = max((t["pnl"] for t in wins), default=0)
    max_loss = min((t["pnl"] for t in losses), default=0)
    
    data["stats"] = {
        "total_trades": len(trades),
        "closed_trades": len(closed),
        "open_trades": len(trades) - len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_pnl": round(total_pnl, 2),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_win": max_win,
        "max_loss": max_loss,
        "risk_reward": rr_ratio,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
