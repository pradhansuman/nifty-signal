#!/usr/bin/env python3
"""
Intraday Signals — VWAP Reversion + EMA Crossover + 20/50 trend + 20 EMA reclaim.

Data sources:
  - Nifty / BankNifty / Sensex: Upstox REAL-TIME 1m feed (upstox_rt), resampled
    to 5m / 15m. This is live, not Yahoo's ~15-min-delayed NSE bars.
  - 1h 20/50 trend cross: falls back to Yahoo because the real-time feed only
    accumulates ~1-3 days of bars and Upstox /historical-candle is 403 — 55
    hourly bars (~8 sessions) can only come from Yahoo's historical data.
  - BTC is NOT in this module (it has its own Yahoo/Delta monitor and no Indian
    market-hours VWAP/cross concept).

Runs during market hours (9:15 AM - 3:30 PM IST).
"""

import json
import sys
from datetime import datetime

import pandas as pd
import numpy as np
import pytz

import upstox_rt

IST = pytz.timezone("Asia/Kolkata")

# Intraday signals are computed for the three Indian indices (Upstox-fed 5m;
# Yahoo 15m/1h).
ASSETS = ("nifty", "bnf", "sensex")

YAHOO_SYMBOL = {"nifty": "^NSEI", "bnf": "^NSEBANK", "sensex": "^BSESN"}
YAHOO_PERIOD = {"5m": "1d", "15m": "5d", "1h": "60d"}
UPSTOX_RULE = {"5m": "5min", "15m": "15min", "1h": "1h"}


def _market_hours_only(df):
    """Keep only TODAY's 9:15-15:30 IST bars (drop overnight/phantom bars the
    real-time poller can accumulate outside market hours)."""
    if df is None or df.empty:
        return df
    today = datetime.now(IST).date()
    df = df[df.index.date == today]
    if df.empty:
        return df
    return df.between_time("09:15", "15:30")


def _yahoo_bars(symbol, interval):
    try:
        import yfinance as yf
        df = yf.download(symbol, period=YAHOO_PERIOD[interval],
                         interval=interval, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        # Yahoo NSE intraday data is already market-hours-only — do NOT filter
        # to today, or multi-day warmup (15m reclaim needs ~25 bars ≈ 1 session,
        # 1h trend needs 55) is destroyed.
        return df
    except Exception:
        return None


def get_bars(asset, interval="5m"):
    """IST-indexed OHLCV DataFrame for `asset` at `interval` (5m/15m/1h).

    - 5m (VWAP + 9/21 EMA): Upstox REAL-TIME (today's market-hours bars) — the
      actionable intraday signals. Falls back to Yahoo if the feed is thin.
    - 15m (20 EMA reclaim) + 1h (20/50 trend): Yahoo. These need multi-day EMA
      warmup the real-time feed cannot hold (it accumulates ~1-3 days, and
      Upstox /historical-candle is 403).
    """
    if asset in ASSETS and interval == "5m":
        df = upstox_rt.get_bars(asset, UPSTOX_RULE[interval])
        if df is not None and not df.empty:
            df = _market_hours_only(df)
            if len(df) >= 25:
                return df
    return _yahoo_bars(YAHOO_SYMBOL.get(asset, "^NSEI"), interval)


def vwap_signal(df):
    """VWAP mean-reversion: price > VWAP = sell, price < VWAP = buy.

    Index LTP (Upstox) and NSE Yahoo indices have ZERO volume, so volume-weighted
    VWAP would divide by zero. We fall back to a typical-price running mean in
    that case (the correct degenerate behaviour), never NaN."""
    if df is None or df.empty:
        return {"signal": "WAIT", "reason": "No data"}

    closes = df["Close"]
    highs = df["High"]
    lows = df["Low"]
    typical = (highs + lows + closes) / 3.0

    vols = df.get("Volume") if "Volume" in (df.columns if df is not None else []) else None
    has_vol = vols is not None and vols.notna().any() and float(vols.sum()) > 0
    if has_vol:
        vwap = (typical * vols).cumsum() / vols.cumsum()
    else:
        # zero / missing volume → simple typical-price average (never NaN)
        vwap = typical.expanding().mean()

    current = float(closes.iloc[-1])
    vwap_now = float(vwap.iloc[-1])
    if not np.isfinite(vwap_now):
        vwap_now = float(typical.iloc[-1])
    deviation = round((current - vwap_now) / vwap_now * 100, 2)

    result = {
        "signal": "NEUTRAL",
        "vwap": round(vwap_now, 2),
        "spot": round(current, 2),
        "deviation_pct": deviation,
        "reason": "",
    }

    if deviation > 0.5:
        result["signal"] = "VWAP_SELL"
        result["direction"] = "short"
        result["reason"] = f"Price {abs(deviation)}% above VWAP ({vwap_now:.0f}) — revert lower."
    elif deviation < -0.5:
        result["signal"] = "VWAP_BUY"
        result["direction"] = "long"
        result["reason"] = f"Price {abs(deviation)}% below VWAP ({vwap_now:.0f}) — revert higher."
    else:
        result["reason"] = f"Price within 0.5% of VWAP ({vwap_now:.0f}). No edge."

    return result


def ema_signal(df):
    """9/21 EMA crossover on 5-min bars."""
    if df is None or len(df) < 25:
        return {"signal": "WAIT", "reason": "Not enough bars for EMA"}

    closes = df["Close"]
    ema9 = closes.ewm(span=9, adjust=False).mean()
    ema21 = closes.ewm(span=21, adjust=False).mean()

    highs = df["High"].astype(float)
    lows = df["Low"].astype(float)
    pc = closes.shift(1)
    tr = pd.concat([(highs - lows).clip(lower=0), (highs - pc).abs(), (lows - pc).abs()], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else 0.0

    current = float(closes.iloc[-1])
    ema9_now = float(ema9.iloc[-1])
    ema21_now = float(ema21.iloc[-1])

    cross_up = False
    cross_down = False
    if len(ema9) >= 3 and len(ema21) >= 3:
        if float(ema9.iloc[-2]) <= float(ema21.iloc[-2]) and ema9_now > ema21_now:
            cross_up = True
        if float(ema9.iloc[-2]) >= float(ema21.iloc[-2]) and ema9_now < ema21_now:
            cross_down = True

    result = {
        "signal": "NEUTRAL",
        "ema9": round(ema9_now, 2),
        "ema21": round(ema21_now, 2),
        "spot": round(current, 2),
        "atr": round(atr14, 2),
        "reason": "",
    }

    if cross_up:
        result["signal"] = "EMA_BUY"
        result["reason"] = f"Golden cross! 9 EMA ({ema9_now:.0f}) crossed above 21 EMA ({ema21_now:.0f})."
        result["entry"] = round(current, 2)
        result["stop"] = round(current - 1.0 * atr14, 2)
        result["target"] = round(current + 2.0 * atr14, 2)
        result["rr"] = 2.0
        result["exit_rule"] = "9 EMA crosses back below 21 EMA (death cross), or stop/target hit, or 15:20 EOD"
    elif cross_down:
        result["signal"] = "EMA_SELL"
        result["reason"] = f"Death cross! 9 EMA ({ema9_now:.0f}) crossed below 21 EMA ({ema21_now:.0f})."
        result["entry"] = round(current, 2)
        result["stop"] = round(current + 1.0 * atr14, 2)
        result["target"] = round(current - 2.0 * atr14, 2)
        result["rr"] = 2.0
        result["exit_rule"] = "9 EMA crosses back above 21 EMA (golden cross), or stop/target hit, or 15:20 EOD"
    elif ema9_now > ema21_now:
        result["signal"] = "EMA_LONG"
        result["reason"] = f"Uptrend: 9 EMA ({ema9_now:.0f}) > 21 EMA ({ema21_now:.0f}). No fresh cross."
    else:
        result["signal"] = "EMA_SHORT"
        result["reason"] = f"Downtrend: 9 EMA ({ema9_now:.0f}) < 21 EMA ({ema21_now:.0f}). No fresh cross."

    return result


def trend_cross_signal(df):
    """20/50 EMA cross on 1h bars — the trend-change cross."""
    if df is None or len(df) < 55:
        return {"signal": "NEUTRAL", "reason": "Not enough bars for 20/50 cross"}
    closes = df["Close"].astype(float)
    ema20 = closes.ewm(span=20, adjust=False).mean()
    ema50 = closes.ewm(span=50, adjust=False).mean()
    e20_prev, e20_now = float(ema20.iloc[-2]), float(ema20.iloc[-1])
    e50_prev, e50_now = float(ema50.iloc[-2]), float(ema50.iloc[-1])
    current = float(closes.iloc[-1])
    highs = df["High"].astype(float)
    lows = df["Low"].astype(float)
    pc = closes.shift(1)
    tr = pd.concat([(highs - lows).clip(lower=0), (highs - pc).abs(), (lows - pc).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else 0.0
    r = {"signal": "NEUTRAL", "ema20": round(e20_now, 2), "ema50": round(e50_now, 2),
         "spot": round(current, 2), "atr": round(atr, 2), "reason": ""}
    if e20_prev <= e50_prev and e20_now > e50_now:
        r["signal"] = "GOLDEN_CROSS"
        r["reason"] = f"20 EMA ({e20_now:.0f}) crossed above 50 EMA ({e50_now:.0f}) — trend turning UP"
        r["entry"] = round(current, 2)
        r["stop"] = round(current - 1.0 * atr, 2)
        r["target"] = round(current + 2.0 * atr, 2)
        r["rr"] = 2.0
        r["exit_rule"] = "20 EMA crosses back below 50 EMA (death cross), or stop/target hit"
    elif e20_prev >= e50_prev and e20_now < e50_now:
        r["signal"] = "DEATH_CROSS"
        r["reason"] = f"20 EMA ({e20_now:.0f}) crossed below 50 EMA ({e50_now:.0f}) — trend turning DOWN"
        r["entry"] = round(current, 2)
        r["stop"] = round(current + 1.0 * atr, 2)
        r["target"] = round(current - 2.0 * atr, 2)
        r["rr"] = 2.0
        r["exit_rule"] = "20 EMA crosses back above 50 EMA (golden cross), or stop/target hit"
    return r


def ema20_reclaim_signal(df):
    """Spot reclaiming (bullish) / losing (bearish) the 20 EMA on 15m bars."""
    if df is None or len(df) < 25:
        return {"signal": "NEUTRAL", "reason": "Not enough bars for 20 EMA reclaim"}
    closes = df["Close"].astype(float)
    ema20 = closes.ewm(span=20, adjust=False).mean()
    spot_prev, spot_now = float(closes.iloc[-2]), float(closes.iloc[-1])
    e20_prev, e20_now = float(ema20.iloc[-2]), float(ema20.iloc[-1])
    highs = df["High"].astype(float)
    lows = df["Low"].astype(float)
    pc = closes.shift(1)
    tr = pd.concat([(highs - lows).clip(lower=0), (highs - pc).abs(), (lows - pc).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else 0.0
    r = {"signal": "NEUTRAL", "ema20": round(e20_now, 2), "spot": round(spot_now, 2),
         "atr": round(atr, 2), "reason": ""}
    if spot_prev <= e20_prev and spot_now > e20_now:
        r["signal"] = "RECLAIM"
        r["reason"] = f"Spot ({spot_now:.0f}) reclaimed the 20 EMA ({e20_now:.0f}) — bullish entry zone"
        r["entry"] = round(spot_now, 2)
        r["stop"] = round(spot_now - 1.0 * atr, 2)
        r["target"] = round(spot_now + 2.0 * atr, 2)
        r["rr"] = 2.0
        r["exit_rule"] = "Spot closes back below the 20 EMA, or stop/target hit, or 15:20 EOD"
    elif spot_prev >= e20_prev and spot_now < e20_now:
        r["signal"] = "LOSS"
        r["reason"] = f"Spot ({spot_now:.0f}) lost the 20 EMA ({e20_now:.0f}) — bearish"
        r["entry"] = round(spot_now, 2)
        r["stop"] = round(spot_now + 1.0 * atr, 2)
        r["target"] = round(spot_now - 2.0 * atr, 2)
        r["rr"] = 2.0
        r["exit_rule"] = "Spot closes back above the 20 EMA, or stop/target hit, or 15:20 EOD"
    return r


def compute(asset="nifty"):
    """Compute the 4 intraday signals for one asset (flat dict)."""
    now = datetime.now(IST)

    result = {
        "asset": asset,
        "timestamp": now.strftime("%H:%M:%S"),
        "market_open": False,
        "vwap": None,
        "ema": None,
        "trend": None,
        "ema20": None,
    }

    if now.weekday() >= 5:
        result["reason"] = "Market closed (weekend)"
        return result

    mkt_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    mkt_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    if now < mkt_open or now > mkt_close:
        result["reason"] = "Outside market hours (9:15 AM - 3:30 PM IST)"
        return result

    result["market_open"] = True

    try:
        df = get_bars(asset, "5m")
        result["vwap"] = vwap_signal(df)
        result["ema"] = ema_signal(df)
    except Exception as e:
        result["error"] = str(e)

    try:
        result["trend"] = trend_cross_signal(get_bars(asset, "1h"))
    except Exception as e:
        result["trend_error"] = str(e)

    try:
        result["ema20"] = ema20_reclaim_signal(get_bars(asset, "15m"))
    except Exception as e:
        result["ema20_error"] = str(e)

    return result


def main():
    """Backward-compatible entry: return NIFTY's flat signal dict.

    All existing in-process consumers (run_script → main) — /api/regime,
    /api/trade-gate, and the cross/reclaim alert scheduler — expect this shape
    and stay Nifty-only."""
    return compute("nifty")


def main_all():
    """All three indices, for a single multi-asset fetch."""
    return {a: compute(a) for a in ASSETS}


if __name__ == "__main__":
    asset = sys.argv[1] if len(sys.argv) > 1 else "nifty"
    r = main_all() if asset == "all" else compute(asset)
    print(json.dumps(r, indent=2, default=str))
