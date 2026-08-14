#!/usr/bin/env python3
"""
Nifty Scalper — 5-min momentum scalp engine with actionable Buy CE/PE calls.

Combines: 9/21 EMA cross, session VWAP, RSI(14), Stoch(14,3), 3-bar momentum,
and the opening range (first 15 min) into a LONG/SHORT/FLAT bias with a score.
When the bias is strong enough, builds a concrete option call (ATM strike,
live premium from the Upstox chain, entry/target/stop on the premium).

Output: JSON for GET /api/scalper (cached 30s server-side).
"""

import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import pytz
import yfinance as yf

sys.path.insert(0, ".")
import chain_table  # noqa: E402  (Upstox option chain for live premiums)

SYMBOL = "^NSEI"
IST = pytz.timezone("Asia/Kolkata")
LOT = 65


def _now():
    return datetime.now(IST).strftime("%H:%M:%S")


def get_bars(period="5d", interval="5m"):
    df = yf.download(SYMBOL, period=period, interval=interval, progress=False, auto_adjust=True)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)
    return df


def _rsi(closes, n=14):
    delta = closes.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ru = up.ewm(alpha=1 / n, adjust=False).mean()
    rd = down.ewm(alpha=1 / n, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _stoch(df, k=14, d=3):
    low = df["Low"].rolling(k).min()
    high = df["High"].rolling(k).max()
    kk = 100 * (df["Close"] - low) / (high - low).replace(0, np.nan)
    return kk, kk.rolling(d).mean()


def build_call(spot, bias, expiry):
    """Spread-aware strike selection: prefer delta 0.40-0.80 with the tightest spread;
    block the call entirely when the spread is > 3% of premium (target can't beat it)."""
    try:
        ch = chain_table.get_chain()
        rows = ch.get("rows") or []
        if not rows:
            return None
        cands = []
        for r in rows:
            strike = r.get("strike") or 0
            if bias == "LONG":
                ltp, bid, ask, delta = r.get("ce_ltp"), r.get("ce_bid"), r.get("ce_ask"), r.get("ce_delta")
            else:
                ltp, bid, ask, delta = r.get("pe_ltp"), r.get("pe_bid"), r.get("pe_ask"), r.get("pe_delta")
            if not ltp or ltp <= 0:
                continue
            if delta is not None and not (0.40 <= abs(delta) <= 0.80):
                continue
            if bid and ask and ask > bid:
                spread = float(ask) - float(bid)
            else:
                spread = float(ltp) * 0.02  # estimate when no quote
            cands.append({
                "strike": strike, "ltp": float(ltp), "spread": spread,
                "spread_pct": spread / float(ltp) * 100,
                "delta": float(delta) if delta is not None else None,
            })
        if not cands:
            return None
        cands.sort(key=lambda c: c["spread_pct"])
        best = cands[0]
        if best["spread_pct"] > 3.0:
            return {"blocked": True, "block_reason":
                    "spread {:.1f}% of premium — target +10% can't beat it".format(best["spread_pct"])}
        prem = best["ltp"]
        return {
            "option": "Buy {:,} {}".format(best["strike"], "CE" if bias == "LONG" else "PE"),
            "strike": best["strike"],
            "premium": round(prem, 2),
            "expiry": ch.get("expiry") or expiry,
            "entry": round(prem, 2),
            "target": round(prem * 1.10, 2),
            "stop": round(prem * 0.90, 2),
            "lot_cost": round(prem * LOT, 0),
            "spread": round(best["spread"], 2),
            "spread_pct": round(best["spread_pct"], 2),
            "delta": best["delta"],
            "target_pts": round(spot * 0.0015, 0),
            "stop_pts": round(spot * 0.0009, 0),
        }
    except Exception:
        return None
    return None


def main():
    out = {"signal": "WAIT", "bias": "FLAT", "score": 0, "spot": None, "timestamp": _now()}
    df = get_bars()
    if df is None or len(df) < 40:
        out["reason"] = "Not enough 5m bars yet (need 40, market opens 9:15 IST)"
        return out

    # Session split: indicators warm on 5 days of bars; VWAP/ORB/spot use today only
    today = df.index.date[-1]
    sess = df[df.index.date == today]
    if len(sess) < 3:
        out["reason"] = "Today's session just started ({} bars so far)".format(len(sess))
        return out

    closes = df["Close"]
    highs = df["High"]
    lows = df["Low"]
    s_close = sess["Close"]
    s_high = sess["High"]
    s_low = sess["Low"]
    spot = float(s_close.iloc[-1])
    out["spot"] = round(spot, 2)

    ema9 = closes.ewm(span=9, adjust=False).mean()
    ema21 = closes.ewm(span=21, adjust=False).mean()
    e9 = float(ema9.iloc[-1])
    e21 = float(ema21.iloc[-1])

    cross_up = cross_down = False
    for i in (2, 1):
        prev9, prev21 = float(ema9.iloc[-i - 1]), float(ema21.iloc[-i - 1])
        cur9, cur21 = float(ema9.iloc[-i]), float(ema21.iloc[-i])
        if prev9 <= prev21 and cur9 > cur21:
            cross_up = True
        if prev9 >= prev21 and cur9 < cur21:
            cross_down = True

    typical = (s_high + s_low + s_close) / 3
    vols = sess["Volume"].fillna(0)
    if float(vols.sum()) > 0:
        vwap = (typical * vols).cumsum() / vols.cumsum()
    else:
        # No volume from yfinance — fall back to expanding typical-price VWAP
        vwap = typical.expanding().mean()
    vwap_now = float(vwap.iloc[-1])

    r = float(_rsi(closes).iloc[-1])
    kk, dd = _stoch(df)
    k = float(kk.iloc[-1])
    dline = float(dd.iloc[-1])

    mom = float(closes.iloc[-1] - closes.iloc[-4])
    n_orb = min(3, len(sess))
    orb_high = float(s_high.iloc[:n_orb].max())
    orb_low = float(s_low.iloc[:n_orb].min())

    score = 0
    reasons = []
    if e9 > e21:
        score += 2
        reasons.append("EMA9 {:.0f} > EMA21 {:.0f}".format(e9, e21))
    else:
        score -= 2
        reasons.append("EMA9 {:.0f} < EMA21 {:.0f}".format(e9, e21))
    if cross_up:
        score += 2
        reasons.append("fresh golden cross")
    if cross_down:
        score -= 2
        reasons.append("fresh death cross")
    if spot > vwap_now:
        score += 1
        reasons.append("above VWAP {:.0f}".format(vwap_now))
    else:
        score -= 1
        reasons.append("below VWAP {:.0f}".format(vwap_now))
    if mom > 0:
        score += 1
        reasons.append("momentum +{:.1f}".format(mom))
    else:
        score -= 1
        reasons.append("momentum {:.1f}".format(mom))
    if r > 70:
        score -= 1
        reasons.append("RSI {:.0f} overbought".format(r))
    elif r < 30:
        score += 1
        reasons.append("RSI {:.0f} oversold".format(r))
    else:
        reasons.append("RSI {:.0f} neutral".format(r))
    if k > 80:
        score -= 1
        reasons.append("Stoch {:.0f} overbought".format(k))
    elif k < 20:
        score += 1
        reasons.append("Stoch {:.0f} oversold".format(k))
    else:
        reasons.append("Stoch {:.0f} neutral".format(k))
    if spot > orb_high:
        score += 1
        reasons.append("above ORB high {:.0f}".format(orb_high))
    elif spot < orb_low:
        score -= 1
        reasons.append("below ORB low {:.0f}".format(orb_low))

    bias = "LONG" if score >= 3 else "SHORT" if score <= -3 else "FLAT"

    # ── 200 EMA regime filter: never scalp against the trend ──
    ema200 = float(closes.ewm(span=200, adjust=False).mean().iloc[-1])
    out["ema200"] = round(ema200, 2)
    regime_block = None
    if bias == "LONG" and spot < ema200:
        regime_block = "counter-trend LONG blocked (spot below 200 EMA {:.0f})".format(ema200)
        bias = "FLAT"
    elif bias == "SHORT" and spot > ema200:
        regime_block = "counter-trend SHORT blocked (spot above 200 EMA {:.0f})".format(ema200)
        bias = "FLAT"

    # ── Trend-strength gate: momentum edge exists ONLY on strong-trend days ──
    # Backtest 2026-08-14 (58 sessions, 4295 bars): |spot-200E| >= 0.8% of spot →
    # 134 trades, 60% WR, PF 1.53, +429 pts. Below 0.5% → PF ~0.93 (loser).
    trend_min = float(os.environ.get("SCALP_TREND_MIN", "0.8"))
    trend_dist = abs(spot - ema200) / ema200 * 100.0
    out["trend_dist"] = round(trend_dist, 2)
    out["trend_gate"] = trend_min
    trend_block = None
    if bias != "FLAT" and trend_dist < trend_min:
        trend_block = "trend too weak (|spot-200E| {:.2f}% < {:.1f}% gate) — momentum has no edge in chop".format(
            trend_dist, trend_min)
        bias = "FLAT"

    # ── Time-of-day window: avoid lunch chop ──
    now_dt = datetime.now(IST)
    hm = now_dt.hour * 60 + now_dt.minute
    window_open = (9 * 60 + 20) <= hm <= (11 * 60 + 45) or (13 * 60 + 30) <= hm <= (15 * 60 + 20)
    out["window"] = "ACTIVE" if window_open else "BLOCKED"
    out["window_reason"] = (
        "Scalp window ACTIVE (9:20-11:45, 13:30-15:20)" if window_open
        else "Scalp window BLOCKED — lunch chop 11:45-13:30 / pre-9:20")
    window_block = None
    if not window_open and bias != "FLAT":
        window_block = out["window_reason"]
        bias = "FLAT"

    out.update({
        "bias": bias, "score": score,
        "ema9": round(e9, 2), "ema21": round(e21, 2),
        "vwap": round(vwap_now, 2), "rsi": round(r, 1),
        "stoch_k": round(k, 1), "stoch_d": round(dline, 1),
        "momentum": round(mom, 2), "orb_high": round(orb_high, 2), "orb_low": round(orb_low, 2),
        "reasons": reasons,
        "reason": "; ".join(reasons),
    })

    if bias == "FLAT":
        out["signal"] = "WAIT"
        block_txt = regime_block or trend_block or window_block
        out["reason"] = "No scalp edge — score {:+d} (need ±3). {}{}".format(
            score, (block_txt + ". " if block_txt else ""), "; ".join(reasons))
        return out

    out["signal"] = "SCALP_LONG" if bias == "LONG" else "SCALP_SHORT"
    out["confidence"] = min(100, abs(score) * 14)
    call = build_call(spot, bias, out.get("expiry"))
    out["call"] = call
    if call is None:
        out["reason"] = "{} scalp (score {:+d}) but no option premium available from Upstox chain".format(bias, score)
    elif call.get("blocked"):
        out["reason"] = "{} scalp (score {:+d}) but NO TRADE — {}".format(bias, score, call.get("block_reason", ""))
    else:
        # 10-minute signal freshness window
        from datetime import timedelta
        call["expires_at"] = (now_dt + timedelta(minutes=10)).strftime("%H:%M")
        out["reason"] = "{} scalp — score {:+d}. {}".format(bias, score, "; ".join(reasons))
    return out


if __name__ == "__main__":
    print(json.dumps(main(), default=str))
