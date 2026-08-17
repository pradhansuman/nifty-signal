#!/usr/bin/env python3
"""
Intraday Signals — VWAP Reversion + EMA Crossover
Runs on 5-min Nifty bars during market hours (9:15 AM - 3:30 PM IST).
"""

import json, sys
from datetime import datetime
import pytz
import yfinance as yf
import pandas as pd
import numpy as np

SYMBOL = "^NSEI"
IST = pytz.timezone("Asia/Kolkata")


def get_intraday(period="1d", interval="5m"):
    t = yf.Ticker(SYMBOL)
    df = yf.download(SYMBOL, period=period, interval=interval, progress=False, auto_adjust=True)
    if df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)
    return df


def vwap_signal(df):
    """VWAP mean-reversion: price > VWAP = sell, price < VWAP = buy."""
    if df is None or df.empty:
        return {"signal": "WAIT", "reason": "No data"}
    
    closes = df["Close"]
    highs = df["High"]; lows = df["Low"]
    
    if "Volume" not in df.columns:
        # Estimate typical price VWAP without volume
        typical = (highs + lows + closes) / 3
        vwap = typical.expanding().mean()
    else:
        vols = df["Volume"]
        typical = (highs + lows + closes) / 3
        vwap = (typical * vols).cumsum() / vols.cumsum()
    
    current = closes.iloc[-1]
    vwap_now = vwap.iloc[-1]
    deviation = round((current - vwap_now) / vwap_now * 100, 2)
    
    result = {
        "signal": "NEUTRAL",
        "vwap": round(float(vwap_now), 2),
        "spot": round(float(current), 2),
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

    # ATR(14) on 5m bars — volatility-scaled stop/target distance
    highs = df["High"].astype(float)
    lows = df["Low"].astype(float)
    pc = closes.shift(1)
    tr = pd.concat([(highs - lows).clip(lower=0), (highs - pc).abs(), (lows - pc).abs()], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else 0.0

    current = float(closes.iloc[-1])
    ema9_now = float(ema9.iloc[-1])
    ema21_now = float(ema21.iloc[-1])
    
    # Check last 3 bars for crossover
    cross_up = False; cross_down = False
    if len(ema9) >= 3 and len(ema21) >= 3:
        # Golden cross: ema9 crosses above ema21
        if float(ema9.iloc[-2]) <= float(ema21.iloc[-2]) and ema9_now > ema21_now:
            cross_up = True
        # Death cross: ema9 crosses below ema21
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
    highs = df["High"].astype(float); lows = df["Low"].astype(float); pc = closes.shift(1)
    tr = pd.concat([(highs - lows).clip(lower=0), (highs - pc).abs(), (lows - pc).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else 0.0
    r = {"signal": "NEUTRAL", "ema20": round(e20_now, 2), "ema50": round(e50_now, 2),
         "spot": round(current, 2), "atr": round(atr, 2), "reason": ""}
    if e20_prev <= e50_prev and e20_now > e50_now:
        r["signal"] = "GOLDEN_CROSS"
        r["reason"] = f"20 EMA ({e20_now:.0f}) crossed above 50 EMA ({e50_now:.0f}) — trend turning UP"
        r["entry"] = round(current, 2); r["stop"] = round(current - 1.0 * atr, 2)
        r["target"] = round(current + 2.0 * atr, 2); r["rr"] = 2.0
        r["exit_rule"] = "20 EMA crosses back below 50 EMA (death cross), or stop/target hit"
    elif e20_prev >= e50_prev and e20_now < e50_now:
        r["signal"] = "DEATH_CROSS"
        r["reason"] = f"20 EMA ({e20_now:.0f}) crossed below 50 EMA ({e50_now:.0f}) — trend turning DOWN"
        r["entry"] = round(current, 2); r["stop"] = round(current + 1.0 * atr, 2)
        r["target"] = round(current - 2.0 * atr, 2); r["rr"] = 2.0
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
    highs = df["High"].astype(float); lows = df["Low"].astype(float); pc = closes.shift(1)
    tr = pd.concat([(highs - lows).clip(lower=0), (highs - pc).abs(), (lows - pc).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else 0.0
    r = {"signal": "NEUTRAL", "ema20": round(e20_now, 2), "spot": round(spot_now, 2),
         "atr": round(atr, 2), "reason": ""}
    if spot_prev <= e20_prev and spot_now > e20_now:
        r["signal"] = "RECLAIM"
        r["reason"] = f"Spot ({spot_now:.0f}) reclaimed the 20 EMA ({e20_now:.0f}) — bullish entry zone"
        r["entry"] = round(spot_now, 2); r["stop"] = round(spot_now - 1.0 * atr, 2)
        r["target"] = round(spot_now + 2.0 * atr, 2); r["rr"] = 2.0
        r["exit_rule"] = "Spot closes back below the 20 EMA, or stop/target hit, or 15:20 EOD"
    elif spot_prev >= e20_prev and spot_now < e20_now:
        r["signal"] = "LOSS"
        r["reason"] = f"Spot ({spot_now:.0f}) lost the 20 EMA ({e20_now:.0f}) — bearish"
        r["entry"] = round(spot_now, 2); r["stop"] = round(spot_now + 1.0 * atr, 2)
        r["target"] = round(spot_now - 2.0 * atr, 2); r["rr"] = 2.0
        r["exit_rule"] = "Spot closes back above the 20 EMA, or stop/target hit, or 15:20 EOD"
    return r


def main():
    now = datetime.now(IST)
    
    result = {
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
        df = get_intraday(period="1d", interval="5m")
        result["vwap"] = vwap_signal(df)
        result["ema"] = ema_signal(df)
    except Exception as e:
        result["error"] = str(e)

    # 20/50 trend cross on 1h + 20 EMA reclaim on 15m (independent fetches)
    try:
        result["trend"] = trend_cross_signal(get_intraday(period="60d", interval="1h"))
    except Exception as e:
        result["trend_error"] = str(e)
    try:
        result["ema20"] = ema20_reclaim_signal(get_intraday(period="5d", interval="15m"))
    except Exception as e:
        result["ema20_error"] = str(e)
    
    return result


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2, default=str))
