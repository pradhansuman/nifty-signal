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

# Timeframe presets per asset: interval -> (period, points)
TIMEFRAMES = {
    "nifty": {"1d": ("1y", 120), "1h": ("1mo", 110), "15m": ("5d", 110),
              "5m": ("1mo", 140), "2m": ("5d", 130), "1m": ("2d", 130)},
    "btc": {"4h": ("2mo", 168), "1h": ("10d", 168), "15m": ("5d", 120),
             "5m": ("1mo", 140), "2m": ("5d", 130), "1m": ("2d", 130)},
    "banknifty": {"1h": ("10d", 110), "15m": ("5d", 110),
                   "5m": ("1mo", 140), "2m": ("5d", 130), "1m": ("2d", 130)},
}
_cache = {"ts": {}, "data": {}}


def get_chart_data(asset="nifty", interval=None, force=False):
    cfg = ASSETS.get(asset)
    if not cfg:
        return {"error": f"Unknown asset {asset}"}
    # Resolve timeframe preset (default = signal timeframe)
    if interval:
        tf = TIMEFRAMES.get(asset, {}).get(interval)
        if not tf:
            return {"error": f"Unknown interval {interval} for {asset}"}
        period, points = tf
    else:
        period, points = cfg["period"], cfg["points"]
        interval = cfg["interval"]
    key = f"{asset}:{interval}"
    now = time.time()
    if not force and _cache["data"].get(key) and (now - _cache["ts"].get(key, 0)) < CACHE_TTL:
        return _cache["data"][key]

    out = {"error": None, "asset": asset, "dates": [], "close": [], "ema200": [], "ema20": [], "spot": None,
           "open": [], "high": [], "low": [], "volume": []}
    try:
        df = yf.download(cfg["symbol"], period=period, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            out["error"] = "No data"
            return out
        if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)
        close = df["Close"].dropna()
        ema = close.ewm(span=200, adjust=False).mean()
        ema20 = close.ewm(span=20, adjust=False).mean()

        tail = close.tail(points)
        ema_tail = ema.tail(points)
        ema20_tail = ema20.tail(points)
        idx = tail.index
        out["dates"] = [str(d) for d in idx]
        out["close"] = [round(float(x), 2) for x in tail.tolist()]
        out["open"] = [round(float(df.loc[d, "Open"]), 2) for d in idx]
        out["high"] = [round(float(df.loc[d, "High"]), 2) for d in idx]
        out["low"] = [round(float(df.loc[d, "Low"]), 2) for d in idx]
        out["volume"] = [int(df.loc[d, "Volume"] or 0) for d in idx]
        out["ema200"] = [round(float(x), 2) if not pd.isna(x) else None for x in ema_tail.tolist()]
        out["ema20"] = [round(float(x), 2) if not pd.isna(x) else None for x in ema20_tail.tolist()]
        out["spot"] = round(float(close.iloc[-1]), 2)
        out["interval"] = interval
    except Exception as e:
        out["error"] = str(e)[:100]

    _cache["ts"][key] = now
    _cache["data"][key] = out
    return out


if __name__ == "__main__":
    import sys
    a = sys.argv[1] if len(sys.argv) > 1 else "nifty"
    d = get_chart_data(a, force=True)
    print(f"{a}: {len(d['close'])} pts, spot {d.get('spot')}" if "error" not in d else d)
