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


def get_expiry(force=False):
    now = time.time()
    if not force and _cache["data"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    today = datetime.now()
    weekly = _next_weekday(1)  # Tuesday
    monthly = _last_tuesday_of_month(today)

    out = {
        "today": today.strftime("%d-%b-%Y %H:%M"),
        "weekly_expiry": weekly.strftime("%d-%b-%Y"),
        "weekly_days": (weekly.date() - today.date()).days,
        "monthly_expiry": monthly.strftime("%d-%b-%Y"),
        "monthly_days": (monthly.date() - today.date()).days,
        "gamma_risk": "low",
        "gamma_note": "",
        "is_expiry_day": today.weekday() == 1,  # Tuesday
        "read": "",
    }

    # Gamma risk: rises sharply on expiry day and day before
    if out["weekly_days"] == 0:
        out["gamma_risk"] = "extreme"
        out["gamma_note"] = "TODAY is weekly expiry! Gamma explodes — close or roll positions by 3:15 PM."
    elif out["weekly_days"] == 1:
        out["gamma_risk"] = "high"
        out["gamma_note"] = "Expiry TOMORROW. Options decay fast — avoid holding OTM positions overnight."
    elif out["weekly_days"] <= 3:
        out["gamma_risk"] = "medium"
        out["gamma_note"] = f"{out['weekly_days']} days to weekly expiry — theta accelerating, prefer ATM or wait for new weekly."
    else:
        out["gamma_risk"] = "low"
        out["gamma_note"] = f"{out['weekly_days']} days to weekly expiry — theta mild, ATM buying is fine."

    out["read"] = f"Weekly expiry {out['weekly_expiry']} in {out['weekly_days']}d · Monthly {out['monthly_expiry']} in {out['monthly_days']}d — {out['gamma_note']}"

    _cache["ts"] = now
    _cache["data"] = out
    return out


if __name__ == "__main__":
    print(json.dumps(get_expiry(force=True), indent=1))
