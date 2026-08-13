#!/usr/bin/env python3
"""
Sensex (BSE SENSEX) 200 EMA Bounce Monitor — same engine as BTC/BNF, for ^BSESN.
- BUY_LONG: 200 EMA bounce with bullish trend (1h bars)
- BUY_SHORT: 200 EMA breakdown with bearish trend
- WAIT: no clear signal
Sensex is an index (no options traded here) — levels are informational.
"""
import json, math
from datetime import datetime
import yfinance as yf
import pandas as pd

SYMBOL = "^BSESN"
ENTRY_ZONE_PCT = 0.5       # within 0.5% of 200 EMA for entry
MIN_ADX = 18
MAX_RSI = 70
MIN_RSI = 30
BROKEN_BELOW_PCT = -0.8
BROKEN_ABOVE_PCT = 0.8
ADX_WEAKENING = 15


def rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    s = pd.Series(prices)
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-10)
    return float(100 - (100 / (1 + rs)).iloc[-1]) if not math.isnan(100 - (100 / (1 + rs)).iloc[-1]) else None


def adx_di(high, low, close, period=14):
    n = len(close)
    if n < period * 2:
        return None, None, None
    up = [0.0] * n
    dn = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)
        up[i] = high[i] - high[i - 1] if high[i] - high[i - 1] > 0 else 0.0
        dn[i] = low[i - 1] - low[i] if low[i - 1] - low[i] > 0 else 0.0
    atr = pd.Series(tr).ewm(alpha=1 / period, adjust=False).mean()
    sup = pd.Series(up).ewm(alpha=1 / period, adjust=False).mean()
    sdn = pd.Series(dn).ewm(alpha=1 / period, adjust=False).mean()
    pdi = 100 * sup / atr.replace(0, 1e-10)
    mdi = 100 * sdn / atr.replace(0, 1e-10)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, 1e-10)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return float(adx.iloc[-1]), float(pdi.iloc[-1]), float(mdi.iloc[-1])


def get_sensex_signal(interval="1h"):
    result = {
        "signal": "WAIT", "reason": "Waiting for setup",
        "spot": None, "ema_200": None, "ema_distance": None, "ema_distance_pct": None,
        "adx": None, "rsi": None, "di_plus": None, "di_minus": None,
        "atr": None, "stop_level": None, "target_level": None,
        "change_pct": None, "entry_zone": False, "trend_broken": False,
        "interval": interval,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M IST"),
    }
    try:
        period = "3mo" if interval == "1h" else "1mo"
        df = yf.download(SYMBOL, period=period, interval=interval, progress=False, auto_adjust=False)
        if df is None or df.empty:
            result["reason"] = "No data from Yahoo"; return result
        # Flatten MultiIndex columns (newer yfinance)
        if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)
        close = df["Close"].dropna()
        high = df["High"].dropna()
        low = df["Low"].dropna()
        if len(close) < 220:
            result["reason"] = f"Insufficient data ({len(close)} bars)"; return result

        ema_200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
        spot = float(close.iloc[-1])
        prev_close = float(close.iloc[-2]) if len(close) > 1 else spot
        atr = float((pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)).ewm(alpha=1/14, adjust=False).mean().iloc[-1])

        adx_val, pdi, mdi = adx_di(high.tolist(), low.tolist(), close.tolist())
        rsi_val = rsi(close.tolist())

        distance_pct = (spot - ema_200) / ema_200 * 100
        result.update({
            "spot": round(spot, 1), "ema_200": round(ema_200, 1),
            "ema_distance_pct": round(distance_pct, 2),
            "adx": round(adx_val, 1) if adx_val else None,
            "rsi": round(rsi_val, 1) if rsi_val else None,
            "di_plus": round(pdi, 1) if pdi else None,
            "di_minus": round(mdi, 1) if mdi else None,
            "atr": round(atr, 1) if atr else None,
            "change_pct": round((spot - prev_close) / prev_close * 100, 2),
            "entry_zone": abs(distance_pct) <= ENTRY_ZONE_PCT,
        })

        # ── Signal logic (identical engine to BTC/BNF) ──
        if distance_pct < BROKEN_BELOW_PCT and adx_val and adx_val > MIN_ADX:
            result["signal"] = "BUY_SHORT"
            result["reason"] = f"Broke 200 EMA by {abs(distance_pct):.2f}% with ADX {adx_val:.0f} — breakdown confirmed"
            result["trend_broken"] = True
        elif distance_pct > BROKEN_ABOVE_PCT and adx_val and adx_val > MIN_ADX and rsi_val and rsi_val > 30:
            result["signal"] = "BUY_LONG"
            result["reason"] = f"Reclaimed above 200 EMA by {distance_pct:.2f}% with ADX {adx_val:.0f} — bounce confirmed"
        elif distance_pct > 0 and distance_pct <= ENTRY_ZONE_PCT and adx_val and adx_val >= MIN_ADX and rsi_val and rsi_val < MAX_RSI:
            result["signal"] = "BUY_LONG"
            result["reason"] = f"200 EMA bounce zone (+{distance_pct:.2f}%), ADX {adx_val:.0f}, RSI {rsi_val:.0f} — bounce entry"
        elif distance_pct < 0 and distance_pct >= -ENTRY_ZONE_PCT and adx_val and adx_val >= MIN_ADX and rsi_val and rsi_val > MIN_RSI:
            result["signal"] = "BUY_SHORT"
            result["reason"] = f"200 EMA breakdown zone ({distance_pct:.2f}%), ADX {adx_val:.0f}, RSI {rsi_val:.0f} — breakdown entry"
        elif adx_val and adx_val < ADX_WEAKENING and result.get("trend_broken"):
            result["signal"] = "EXIT_SHORTS"
            result["reason"] = f"ADX dropped to {adx_val:.0f} — trend dying, cover shorts"
        elif result.get("trend_broken"):
            result["signal"] = "EXIT_LONGS"
            result["reason"] = "Trend broken below 200 EMA — exit longs"
        else:
            result["signal"] = "WAIT"
            result["reason"] = f"No setup — {distance_pct:+.2f}% from 200 EMA, ADX {adx_val:.0f}" if adx_val else "Computing..."

        # Stops/targets (ATR-based, informational — index levels)
        if atr and spot:
            if result["signal"] in ("BUY_LONG",):
                result["stop_level"] = round(spot - 1.5 * atr, 1)
                result["target_level"] = round(spot + 2.5 * atr, 1)
            elif result["signal"] in ("BUY_SHORT",):
                result["stop_level"] = round(spot + 1.5 * atr, 1)
                result["target_level"] = round(spot - 2.5 * atr, 1)

        # ── Trade recommendation ──
        rr = None
        action = None
        if result["signal"] == "BUY_LONG" and result.get("stop_level") and result.get("target_level") and spot:
            risk = spot - result["stop_level"]
            rew = result["target_level"] - spot
            if risk > 0:
                rr = round(rew / risk, 2)
                action = "BUY"
                result["recommendation"] = (
                    f"BUY above ~{spot:,.0f} | Stop {result['stop_level']:,.0f} | "
                    f"Target {result['target_level']:,.0f} | Risk {risk:,.0f} pts | R:R {rr}")
        elif result["signal"] == "BUY_SHORT" and result.get("stop_level") and result.get("target_level") and spot:
            risk = result["stop_level"] - spot
            rew = spot - result["target_level"]
            if risk > 0:
                rr = round(rew / risk, 2)
                action = "SELL"
                result["recommendation"] = (
                    f"SELL below ~{spot:,.0f} | Stop {result['stop_level']:,.0f} | "
                    f"Target {result['target_level']:,.0f} | Risk {risk:,.0f} pts | R:R {rr}")
        else:
            result["recommendation"] = (
                f"HOLD — no trade. {result.get('reason', '')[:70]}")
        result["action"] = action or ("HOLD" if result["signal"] == "WAIT" else "EXIT")
        result["rr_ratio"] = rr
    except Exception as e:
        result["signal"] = "ERROR"
        result["reason"] = str(e)[:100]

    return result


if __name__ == "__main__":
    import sys
    iv = sys.argv[1] if len(sys.argv) > 1 else "1h"
    print(json.dumps(get_sensex_signal(iv), indent=1))
