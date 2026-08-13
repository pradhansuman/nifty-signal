#!/usr/bin/env python3
"""
Expiry countdown + gamma risk for Nifty weekly/monthly expiries.
Weekly = next Tuesday, Monthly = last Tuesday of month.
Cached 10 min.
"""
import json, os, time
from datetime import datetime, timedelta

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "expiry_cache.json")
CACHE_TTL = 600
_cache = {"ts": 0, "data": None}


def _next_weekday(day_of_week):
    today = datetime.now()
    days = (day_of_week - today.weekday()) % 7
    if days == 0:
        days = 7
    return today + timedelta(days=days)


def _last_tuesday_of_month(ref):
    # First day of next month, minus one day, then back to Tuesday
    if ref.month == 12:
        nxt = datetime(ref.year + 1, 1, 1)
    else:
        nxt = datetime(ref.year, ref.month + 1, 1)
    last_day = nxt - timedelta(days=1)
    days_back = (last_day.weekday() - 1) % 7
    return last_day - timedelta(days=days_back)


_cache = {"nifty": {"ts": 0, "data": None}, "banknifty": {"ts": 0, "data": None}}


def get_expiry(force=False, asset="nifty"):
    c = _cache.setdefault(asset, {"ts": 0, "data": None})
    now = time.time()
    if not force and c["data"] and (now - c["ts"]) < CACHE_TTL:
        return c["data"]

    today = datetime.now()
    if asset == "nifty":
        weekly = _next_weekday(1)  # Tuesday
    else:
        weekly = None  # Bank Nifty: monthly only
    monthly = _last_tuesday_of_month(today)

    out = {
        "today": today.strftime("%d-%b-%Y %H:%M"),
        "weekly_expiry": weekly.strftime("%d-%b-%Y") if weekly else None,
        "weekly_days": (weekly.date() - today.date()).days if weekly else None,
        "monthly_expiry": monthly.strftime("%d-%b-%Y"),
        "monthly_days": (monthly.date() - today.date()).days,
        "gamma_risk": "low",
        "gamma_note": "",
        "is_expiry_day": today.weekday() == 1,  # Tuesday
        "read": "",
        "asset": asset,
    }

    # Gamma risk: rises sharply on expiry day and day before
    ref_days = out["weekly_days"] if weekly else out["monthly_days"]
    ref_label = "weekly" if weekly else "monthly"
    ref_expiry = out["weekly_expiry"] if weekly else out["monthly_expiry"]
    if ref_days == 0:
        out["gamma_risk"] = "extreme"
        out["gamma_note"] = f"TODAY is {ref_label} expiry! Gamma explodes — close or roll positions by 3:15 PM."
    elif ref_days == 1:
        out["gamma_risk"] = "high"
        out["gamma_note"] = "Expiry TOMORROW. Options decay fast — avoid holding OTM positions overnight."
    elif ref_days <= 3:
        out["gamma_risk"] = "medium"
        out["gamma_note"] = f"{ref_days} days to {ref_label} expiry — theta accelerating, prefer ATM."
    else:
        out["gamma_risk"] = "low"
        out["gamma_note"] = f"{ref_days} days to {ref_label} expiry — theta mild, ATM buying is fine."

    out["read"] = (f"Weekly {out['weekly_expiry']} in {out['weekly_days']}d · " if weekly else "") + \
                  f"Monthly {out['monthly_expiry']} in {out['monthly_days']}d — {out['gamma_note']}"

    c["ts"] = now
    c["data"] = out
    return out


if __name__ == "__main__":
    print(json.dumps(get_expiry(force=True), indent=1))
