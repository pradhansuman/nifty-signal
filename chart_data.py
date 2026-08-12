#!/usr/bin/env python3
"""
Chart data — recent Nifty price series + 200 EMA for the dashboard sparkline.
Returns last ~120 daily closes + EMA line. Cached 10 min.
"""
import json, os, time
import yfinance as yf
import pandas as pd

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "chart_cache.json")
CACHE_TTL = 600

_cache = {"ts": 0, "data": None}


def get_chart_data(force=False):
    now = time.time()
    if not force and _cache["data"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    out = {"error": None, "dates": [], "close": [], "ema200": [], "spot": None}
    try:
        df = yf.download("^NSEI", period="1y", interval="1d", auto_adjust=False)
        if df is None or df.empty:
            out["error"] = "No data"
            return out
        if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)
        close = df["Close"].dropna()
        ema = close.ewm(span=200, adjust=False).mean()

        # Last 120 trading days
        tail = close.tail(120)
        ema_tail = ema.tail(120)
        out["dates"] = [str(d.date()) for d in tail.index]
        out["close"] = [round(float(x), 1) for x in tail.tolist()]
        out["ema200"] = [round(float(x), 1) if not pd.isna(x) else None for x in ema_tail.tolist()]
        out["spot"] = round(float(close.iloc[-1]), 1)
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
    d = get_chart_data(force=True)
    print(json.dumps(d)[:300])
