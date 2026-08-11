#!/usr/bin/env python3
"""
Opening Range Breakout (ORB) Scalp Signal
- Records Nifty high/low from 9:15-9:30 AM IST
- Signals breakout above/below the range
- Valid during market open to 10:15 AM IST
"""

import json, sys, os
from datetime import datetime
import pytz
import yfinance as yf
import pandas as pd

SYMBOL = "^NSEI"
IST = pytz.timezone("Asia/Kolkata")


def get_intraday_data(period="1d", interval="5m"):
    """Fetch 5-min intraday data from Yahoo Finance."""
    t = yf.Ticker(SYMBOL)
    df = yf.download(SYMBOL, period=period, interval=interval, progress=False, auto_adjust=True)
    if df.empty:
        return None
    # Flatten multi-level columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    # Convert index to IST
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)
    return df


def main():
    now = datetime.now(IST)
    today = now.date()
    
    result = {
        "signal": "WAIT",
        "strategy": "ORB",
        "timestamp": now.strftime("%H:%M:%S"),
        "opening_high": None,
        "opening_low": None,
        "spot": None,
        "breakout_direction": None,
        "entry_strike": None,
        "target_strike": None,
        "stop_strike": None,
        "reason": "",
    }
    
    # Only valid Mon-Fri
    if now.weekday() >= 5:
        result["reason"] = "Market closed (weekend)"
        return result
    
    # Only valid between 9:30 and 10:15 AM
    orb_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    orb_end = now.replace(hour=9, minute=30, second=0, microsecond=0)
    signal_end = now.replace(hour=10, minute=15, second=0, microsecond=0)
    
    if now < orb_end:
        result["reason"] = f"Opening range still forming (9:15-9:30). Check back at 9:30 AM."
        return result
    
    if now > signal_end:
        result["reason"] = "ORB window closed. Try tomorrow between 9:30-10:15 AM."
        return result
    
    try:
        df = get_intraday_data(period="1d", interval="5m")
        if df is None or df.empty:
            result["reason"] = "No intraday data available yet"
            return result
        
        # Find 9:15-9:30 candles
        orb_candles = df[(df.index.time >= orb_start.time()) & (df.index.time <= orb_end.time())]
        
        if orb_candles.empty:
            result["reason"] = "Opening range candles not available yet"
            return result
        
        orb_high = float(orb_candles["High"].max())
        orb_low = float(orb_candles["Low"].min())
        current = float(df["Close"].iloc[-1])
        
        result["opening_high"] = round(orb_high, 2)
        result["opening_low"] = round(orb_low, 2)
        result["spot"] = round(current, 2)
        result["range_pts"] = round(orb_high - orb_low, 1)
        
        # Breakout logic: spot must be ABOVE orb_high or BELOW orb_low
        # Add 0.1% buffer to avoid false breakouts
        buffer_pct = 0.001
        buffer_pts = orb_high * buffer_pct
        
        # ATM strike for the option
        atm_strike = round(current / 50) * 50
        
        if current > orb_high + buffer_pts:
            # Bullish breakout
            target = round(current * 1.005, 1)  # 0.5% target
            stop = round(orb_high - buffer_pts, 1)  # Stop back inside range
            result["signal"] = "ORB_BUY"
            result["breakout_direction"] = "bullish"
            result["entry_strike"] = atm_strike
            result["target_strike"] = round(target / 50) * 50
            result["stop_strike"] = round(stop / 50) * 50
            result["target_pct"] = 0.5
            result["reason"] = (
                f"Breakout above {orb_high:.0f} (range: {orb_high-orb_low:.0f} pts). "
                f"Buy {atm_strike} CE, target {target:.0f} (+0.5%), stop {stop:.0f}."
            )
            
        elif current < orb_low - buffer_pts:
            # Bearish breakdown
            target = round(current * 0.995, 1)
            stop = round(orb_low + buffer_pts, 1)
            result["signal"] = "ORB_SELL"
            result["breakout_direction"] = "bearish"
            result["entry_strike"] = atm_strike
            result["target_strike"] = round(target / 50) * 50
            result["stop_strike"] = round(stop / 50) * 50
            result["target_pct"] = 0.5
            result["reason"] = (
                f"Breakdown below {orb_low:.0f} (range: {orb_high-orb_low:.0f} pts). "
                f"Buy {atm_strike} PE, target {target:.0f} (-0.5%), stop {stop:.0f}."
            )
            
        else:
            result["reason"] = (
                f"Inside opening range ({orb_low:.0f}-{orb_high:.0f}). "
                f"Spot {current:.0f}. Waiting for breakout."
            )
    
    except Exception as e:
        result["reason"] = f"Error: {str(e)}"
        result["signal"] = "ERROR"
    
    return result


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2))
