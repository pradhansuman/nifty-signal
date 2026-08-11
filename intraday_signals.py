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
        "reason": "",
    }
    
    if cross_up:
        result["signal"] = "EMA_BUY"
        result["reason"] = f"Golden cross! 9 EMA ({ema9_now:.0f}) crossed above 21 EMA ({ema21_now:.0f})."
    elif cross_down:
        result["signal"] = "EMA_SELL"
        result["reason"] = f"Death cross! 9 EMA ({ema9_now:.0f}) crossed below 21 EMA ({ema21_now:.0f})."
    elif ema9_now > ema21_now:
        result["signal"] = "EMA_LONG"
        result["reason"] = f"Uptrend: 9 EMA ({ema9_now:.0f}) > 21 EMA ({ema21_now:.0f}). No fresh cross."
    else:
        result["signal"] = "EMA_SHORT"
        result["reason"] = f"Downtrend: 9 EMA ({ema9_now:.0f}) < 21 EMA ({ema21_now:.0f}). No fresh cross."
    
    return result


def main():
    now = datetime.now(IST)
    
    result = {
        "timestamp": now.strftime("%H:%M:%S"),
        "market_open": False,
        "vwap": None,
        "ema": None,
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
    
    return result


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2, default=str))
