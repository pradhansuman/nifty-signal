#!/usr/bin/env python3
"""
IV Rank / Percentile for Nifty — uses India VIX history (30-day Nifty implied vol).
- IV Rank: where current IV sits between 52-week low and high (0-100)
- IV Percentile: % of days in last year where IV was BELOW current
For option BUYERS: low rank = cheap premiums (good to buy), high rank = rich premiums (avoid).
Cached 30 min.
"""
import json, os, time
import yfinance as yf
import pandas as pd

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "ivrank_cache.json")
CACHE_TTL = 1800

_cache = {"ts": 0, "data": None}


def get_iv_rank(force=False):
    now = time.time()
    if not force and _cache["data"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    out = {"error": None, "current_vix": None, "high_52w": None, "low_52w": None,
           "iv_rank": None, "iv_percentile": None, "read": "Data unavailable"}

    try:
        hist = yf.Ticker("^INDIAVIX").history(period="1y", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            out["error"] = "No VIX history"
            _cache["ts"], _cache["data"] = now, out
            return out

        if hasattr(hist.columns, "levels") and len(hist.columns.levels) > 1:
            hist.columns = hist.columns.get_level_values(0)

        closes = hist["Close"].dropna()
        if len(closes) < 60:
            out["error"] = "Insufficient VIX history"
            _cache["ts"], _cache["data"] = now, out
            return out

        current = float(closes.iloc[-1])
        high = float(closes.max())
        low = float(closes.min())
        # IV Rank
        rank = round((current - low) / (high - low) * 100, 1) if high > low else None
        # IV Percentile
        percentile = round((closes < current).mean() * 100, 1)

        out.update({
            "current_vix": round(current, 2),
            "high_52w": round(high, 2),
            "low_52w": round(low, 2),
            "iv_rank": rank,
            "iv_percentile": percentile,
        })

        # Read
        if rank is not None:
            if rank <= 20:
                out["read"] = f"IV Rank {rank}% — premiums CHEAP. Great time to BUY options (low IV = low premium)."
            elif rank <= 40:
                out["read"] = f"IV Rank {rank}% — premiums below average. Favourable for buyers."
            elif rank <= 60:
                out["read"] = f"IV Rank {rank}% — premiums neutral. Normal conditions."
            elif rank <= 80:
                out["read"] = f"IV Rank {rank}% — premiums elevated. Be selective buying; expect IV crush."
            else:
                out["read"] = f"IV Rank {rank}% — premiums RICH. Avoid buying; sellers have the edge."
    except Exception as e:
        out["error"] = str(e)[:100]

    _cache["ts"] = now
    _cache["data"] = out
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(out, f)
    except Exception:
        pass
    return out


if __name__ == "__main__":
    print(json.dumps(get_iv_rank(force=True), indent=1))
