#!/usr/bin/env python3
"""
Upstox Real-Time candle feed — replaces delayed Yahoo bars for the scalper.

Polls Upstox /market-quote/ltp every ~10s and aggregates REAL-TIME 1-minute
OHLCV candles in memory (persisted to disk so history survives restarts and
carries across days). The scalper runs its momentum indicators on these fresh
1m bars instead of ~15-min-delayed Yahoo 5m bars.

Why this exists: the user scalps on 5m Yahoo data that is BOTH coarse and
~15 min delayed for NSE. Upstox LTP is real-time. The Analytics token allows
/market-quote/ltp (but NOT /historical-candle — 403), so we build our own
1m candles from live ticks.

Yahoo is used ONLY as a one-time warmup seed (historical bars so EMA/ADX have
history at market open) and as a fallback if Upstox is unreachable. The LIVE
signal is 100% Upstox.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime

import pandas as pd
import pytz

IST = pytz.timezone("Asia/Kolkata")

SYMBOLS = {
    "nifty": "NSE_INDEX|Nifty 50",
    "bnf": "NSE_INDEX|Nifty Bank",
    "sensex": "BSE_INDEX|SENSEX",
}

POLL_SECONDS = 10
MAX_BARS = 2000  # ~3.3 trading days of 1m bars (enough for 200-period EMA)
CANDLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           ".openclaw", "tmp", "rt_candles.json")

# {asset: [[ts_str "%Y-%m-%d %H:%M", open, high, low, close], ...]}
_candles = {a: [] for a in SYMBOLS}
_last_ltp = {a: None for a in SYMBOLS}
_lock = threading.Lock()
_poller_thread = None


def _load():
    try:
        if os.path.exists(CANDLE_PATH):
            with open(CANDLE_PATH) as f:
                saved = json.load(f)
                for a in SYMBOLS:
                    _candles[a] = saved.get(a, [])
    except Exception:
        pass


def _save():
    try:
        with open(CANDLE_PATH, "w") as f:
            json.dump(_candles, f)
    except Exception:
        pass


def _seed_from_yahoo(asset):
    """One-time warmup: backfill today's 1m history from Yahoo (delayed is fine —
    it's history, not the live signal). Only used when persisted candles are thin."""
    ysym = {"nifty": "^NSEI", "bnf": "^NSEBANK", "sensex": "^BSESN"}.get(asset)
    if not ysym:
        return
    try:
        import yfinance as yf
        df = yf.download(ysym, period="5d", interval="1m", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        today = df.index[-1].date()
        bars = []
        for ts, row in df.iterrows():
            if ts.date() != today:
                continue
            bars.append([ts.strftime("%Y-%m-%d %H:%M"),
                         float(row["Open"]), float(row["High"]),
                         float(row["Low"]), float(row["Close"])])
        if bars:
            _candles[asset] = bars
            _save()
    except Exception:
        pass


def _fetch_ltp():
    """Fetch real-time LTP for all configured indices. Returns {asset: price}."""
    from upstox_token import get_token
    tok = get_token()
    if not tok:
        return {}
    out = {}
    try:
        import requests
        keys = ",".join(SYMBOLS.values())
        r = requests.get("https://api.upstox.com/v2/market-quote/ltp",
                         headers={"Authorization": f"Bearer {tok}",
                                  "Accept": "application/json"},
                         params={"instrument_key": keys}, timeout=15)
        if r.status_code != 200:
            return {}
        data = (r.json() or {}).get("data", {})
        for a, key in SYMBOLS.items():
            resp_key = key.replace("|", ":")  # response uses ':' not '|'
            lp = (data.get(resp_key) or {}).get("last_price")
            if lp:
                out[a] = float(lp)
    except Exception:
        pass
    return out


def _tick():
    prices = _fetch_ltp()
    if not prices:
        return
    now = datetime.now(IST)
    ts_str = now.strftime("%Y-%m-%d %H:%M")
    saved = False
    with _lock:
        for a, px in prices.items():
            _last_ltp[a] = px
            bars = _candles[a]
            if bars and bars[-1][0] == ts_str:
                b = bars[-1]
                b[2] = max(b[2], px)
                b[3] = min(b[3], px)
                b[4] = px
            elif bars and bars[-1][0] > ts_str:
                continue  # out-of-order (clock drift) — ignore
            else:
                bars.append([ts_str, px, px, px, px])
                if len(bars) > MAX_BARS:
                    del bars[:len(bars) - MAX_BARS]
                saved = True
    if saved:
        _save()


def _poller():
    while True:
        try:
            _tick()
        except Exception:
            pass
        time.sleep(POLL_SECONDS)


def start():
    """Start the background LTP poller (idempotent). Seed thin history first."""
    global _poller_thread
    _load()
    for a in SYMBOLS:
        # Seed if we have no bars for today yet (first run / fresh day)
        today = datetime.now(IST).strftime("%Y-%m-%d")
        if not any(b[0].startswith(today) for b in _candles[a]):
            _seed_from_yahoo(a)
    if _poller_thread is None or not _poller_thread.is_alive():
        _poller_thread = threading.Thread(target=_poller, daemon=True)
        _poller_thread.start()


def _resample(df, rule):
    if df is None or df.empty or rule in (None, "1min"):
        return df
    return df.resample(rule).agg({"Open": "first", "High": "max",
                                  "Low": "min", "Close": "last"}).dropna()


def get_bars(asset, rule="1min", limit=None):
    """Return a pandas DataFrame of real-time candles for `asset` (IST-indexed).
    rule: pandas resample rule ('1min','5min','15min','1h',...) — resamples the
    1m feed. Returns None if no data yet."""
    if asset not in SYMBOLS:
        return None
    with _lock:
        bars = list(_candles.get(asset, []))
    if limit:
        bars = bars[-limit:]
    if not bars:
        return None
    df = pd.DataFrame([{"ts": b[0], "Open": b[1], "High": b[2],
                        "Low": b[3], "Close": b[4]} for b in bars])
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.set_index("ts")
    df.index = df.index.tz_localize(IST)
    df = _resample(df, rule)
    if df is not None and not df.empty:
        # Upstox index LTP has no volume — provide a zero column so downstream
        # VWAP math (vol-weighted) degrades gracefully to a simple average.
        df["Volume"] = 0.0
    return df


def last_price(asset):
    return _last_ltp.get(asset)


def has_data(asset, min_bars=5):
    with _lock:
        return len(_candles.get(asset, [])) >= min_bars


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    start()
    time.sleep(3)
    for a in SYMBOLS:
        df = get_bars(a)
        n = 0 if df is None else len(df)
        lp = last_price(a)
        print(f"{a}: bars={n} last_price={lp}")
