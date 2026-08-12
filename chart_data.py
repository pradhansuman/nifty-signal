#!/usr/bin/env python3
"""
Chart data — price series + 200 EMA for Nifty / BTC / Bank Nifty.
Nifty: daily (120d) · BTC: 1h (7d ~168 bars) · BNF: 1h (7d ~112 bars)
Cached 10 min per asset.
"""
import json, os, time
import yfinance as yf
import pandas as pd

CACHE_TTL = 600
ASSETS = {
    "nifty": {"symbol": "^NSEI", "period": "1y", "interval": "1d", "points": 120},
    "btc": {"symbol": "BTC-USD", "period": "10d", "interval": "1h", "points": 168},
    "banknifty": {"symbol": "^NSEBANK", "period": "10d", "interval": "1h", "points": 110},
}
_cache = {"ts": {}, "data": {}}


def get_chart_data(asset="nifty", force=False):
    cfg = ASSETS.get(asset)
    if not cfg:
        return {"error": f"Unknown asset {asset}"}
    now = time.time()
    if not force and _cache["data"].get(asset) and (now - _cache["ts"].get(asset, 0)) < CACHE_TTL:
        return _cache["data"][asset]

    out = {"error": None, "asset": asset, "dates": [], "close": [], "ema200": [], "spot": None}
    try:
        df = yf.download(cfg["symbol"], period=cfg["period"], interval=cfg["interval"], auto_adjust=False)
        if df is None or df.empty:
            out["error"] = "No data"
            return out
        if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)
        close = df["Close"].dropna()
        ema = close.ewm(span=200, adjust=False).mean()

        tail = close.tail(cfg["points"])
        ema_tail = ema.tail(cfg["points"])
        out["dates"] = [str(d) for d in tail.index]
        out["close"] = [round(float(x), 2) for x in tail.tolist()]
        out["ema200"] = [round(float(x), 2) if not pd.isna(x) else None for x in ema_tail.tolist()]
        out["spot"] = round(float(close.iloc[-1]), 2)
        out["interval"] = cfg["interval"]
    except Exception as e:
        out["error"] = str(e)[:100]

    _cache["ts"][asset] = now
    _cache["data"][asset] = out
    return out


if __name__ == "__main__":
    import sys
    a = sys.argv[1] if len(sys.argv) > 1 else "nifty"
    d = get_chart_data(a, force=True)
    print(f"{a}: {len(d['close'])} pts, spot {d.get('spot')}" if "error" not in d else d)
