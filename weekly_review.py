#!/usr/bin/env python3
"""
Weekly Review — Friday 3:35 PM auto-report from the trade journal.
Summarizes weekly P&L, win rate, discipline adherence, and best/worst trades.
Pushes to Telegram. Cached.
"""
import json, os
from datetime import datetime, timedelta
from trade_journal import get_all

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "weekly_cache.json")


def _week_key(dt):
    # ISO week
    return dt.isocalendar()[:2]


def build_weekly_report():
    trades = get_all() or []
    now = datetime.now()
    wk = _week_key(now)

    week_trades = []
    for t in trades:
        try:
            ts = t.get("timestamp") or t.get("date") or t.get("entry_time") or ""
            ts = str(ts).replace("Z", "").replace("T", " ")
            dt = datetime.fromisoformat(ts[:19]) if ts else None
        except Exception:
            dt = None
        if dt and _week_key(dt) == wk:
            week_trades.append(t)

    pnl = sum(float(t.get("pnl") or 0) for t in week_trades)
    wins = [t for t in week_trades if float(t.get("pnl") or 0) > 0]
    losses = [t for t in week_trades if float(t.get("pnl") or 0) < 0]
    total_capital = 0

    report = {
        "week": f"{now.isocalendar()[0]}-W{now.isocalendar()[1]}",
        "generated": now.strftime("%Y-%m-%d %H:%M"),
        "trades": len(week_trades),
        "win_rate": round(len(wins) / len(week_trades) * 100, 1) if week_trades else 0,
        "pnl": round(pnl, 1),
        "avg_win": round(sum(float(t.get("pnl") or 0) for t in wins) / len(wins), 1) if wins else 0,
        "avg_loss": round(sum(float(t.get("pnl") or 0) for t in losses) / len(losses), 1) if losses else 0,
        "best": max((float(t.get("pnl") or 0) for t in week_trades), default=0),
        "worst": min((float(t.get("pnl") or 0) for t in week_trades), default=0),
        "read": "",
    }

    # Discipline note
    notes = []
    if report["trades"] == 0:
        notes.append("No trades logged this week. If you traded, log them — the journal is the edge.")
    else:
        if report["win_rate"] >= 50 and report["pnl"] > 0:
            notes.append("Profitable week with discipline. Keep the same process.")
        elif report["pnl"] <= 0:
            notes.append("Losing week — check if stops were respected and sizing was within limits.")
        if report["worst"] < -report["avg_win"] * 1.5 if report["avg_win"] else False:
            notes.append("One loss too big — likely stop not respected or oversized.")
    report["read"] = " ".join(notes) if notes else "Good discipline this week."

    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(report, f, default=str)
    except Exception:
        pass
    return report


def get_weekly_report():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return build_weekly_report()


if __name__ == "__main__":
    print(json.dumps(build_weekly_report(), indent=1))
