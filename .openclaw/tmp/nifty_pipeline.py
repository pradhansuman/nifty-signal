#!/usr/bin/env python3
"""
Nifty 50 Options Analysis Pipeline — 15-step end-to-end
========================================================
Data: Yahoo Finance (^NSEI, ^INDIAVIX) + NSE option chain enrichment
"""

import json
import math
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict
import time
import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import requests

# ─────────────── CONFIG ───────────────
SYMBOL = "^NSEI"
VIX_SYMBOL = "^INDIAVIX"
EXPIRY_DATE_STR = "2026-08-27"
EXPIRY_DISPLAY = "27-Aug-2026"
LOT_SIZE = 25
RISK_FREE = 0.065

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

# ─────────────── FETCH RAW DATA ───────────────

def fetch_all_raw():
    """Fetch all raw data with minimal round-trips."""
    t0 = time.time()
    
    nifty = yf.Ticker(SYMBOL)
    vix_t = yf.Ticker(VIX_SYMBOL)
    
    # ── Nifty fast_info (snake_case attributes) ──
    nf = nifty.fast_info
    nifty_spot = getattr(nf, "last_price", None)
    # fallback to info dict
    if not nifty_spot:
        ninfo = nifty.info or {}
        nifty_spot = ninfo.get("regularMarketPrice") or ninfo.get("currentPrice")
    
    nifty_data = {
        "spot": nifty_spot,
        "prev_close": getattr(nf, "previous_close", None) or getattr(nf, "regular_market_previous_close", None),
        "open": getattr(nf, "open", None),
        "high": getattr(nf, "day_high", None),
        "low": getattr(nf, "day_low", None),
        "fifty_day_avg": getattr(nf, "fifty_day_average", None),
        "two_hundred_day_avg": getattr(nf, "two_hundred_day_average", None),
        "year_high": getattr(nf, "year_high", None),
        "year_low": getattr(nf, "year_low", None),
    }
    
    # ── VIX fast_info ──
    vf = vix_t.fast_info
    vix_val = getattr(vf, "last_price", None)
    vix_data = {
        "vix": vix_val,
        "prev_close": getattr(vf, "previous_close", None) or getattr(vf, "regular_market_previous_close", None),
        "high": getattr(vf, "day_high", None),
        "low": getattr(vf, "day_low", None),
        "fifty_day_avg": getattr(vf, "fifty_day_average", None),
        "two_hundred_day_avg": getattr(vf, "two_hundred_day_average", None),
    }
    
    # ── Historical prices (6 months daily) ──
    print("[DATA] Fetching 6-month history...", file=sys.stderr)
    hist = yf.download(SYMBOL, period="6mo", interval="1d", progress=False, auto_adjust=False)
    # yfinance returns multi-level columns; flatten
    if isinstance(hist.columns, pd.MultiIndex):
        close_col = ("Close", SYMBOL) if ("Close", SYMBOL) in hist.columns else hist.columns[0]
        high_col = ("High", SYMBOL) if ("High", SYMBOL) in hist.columns else None
        low_col = ("Low", SYMBOL) if ("Low", SYMBOL) in hist.columns else None
        vol_col = ("Volume", SYMBOL) if ("Volume", SYMBOL) in hist.columns else None
    else:
        close_col = "Close"
        high_col = "High"
        low_col = "Low"
        vol_col = "Volume"
    closes = pd.Series(hist[close_col]).dropna().values.tolist()
    highs = pd.Series(hist[high_col]).dropna().values.tolist() if high_col else closes
    lows = pd.Series(hist[low_col]).dropna().values.tolist() if low_col else closes
    volumes = pd.Series(hist[vol_col]).dropna().values.tolist() if vol_col and vol_col in hist.columns else []
    
    # ── VIX history (3 months) ──
    vix_hist = yf.download(VIX_SYMBOL, period="3mo", interval="1d", progress=False, auto_adjust=False)
    if isinstance(vix_hist.columns, pd.MultiIndex):
        vix_close_col = ("Close", VIX_SYMBOL) if ("Close", VIX_SYMBOL) in vix_hist.columns else vix_hist.columns[0]
    else:
        vix_close_col = "Close"
    vix_history = pd.Series(vix_hist[vix_close_col]).dropna().values.tolist()
    
    # ── Option chain (best-effort via Yahoo) ──
    option_chain_raw = []
    yf_options = None
    try:
        exp_dates = nifty.options
        if exp_dates:
            for d in exp_dates:
                if EXPIRY_DATE_STR in d:
                    opt = nifty.option_chain(d)
                    yf_options = {
                        "calls": opt.calls.to_dict("records"),
                        "puts": opt.puts.to_dict("records"),
                    }
                    break
    except Exception as e:
        print(f"[DATA] Yahoo options not available: {e}", file=sys.stderr)
    
    # ── NSE option chain enrichment ──
    print("[DATA] Trying NSE option chain...", file=sys.stderr)
    try:
        sess = requests.Session()
        sess.headers.update(NSE_HEADERS)
        sess.get("https://www.nseindia.com", timeout=12)
        resp = sess.get(
            f"https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            timeout=20
        )
        if resp.status_code == 200:
            data = resp.json()
            all_records = data.get("records", {}).get("data", [])
            for entry in all_records:
                ce = entry.get("CE", {})
                pe = entry.get("PE", {})
                if (ce and ce.get("expiryDate") == EXPIRY_DISPLAY) or (pe and pe.get("expiryDate") == EXPIRY_DISPLAY):
                    option_chain_raw.append(entry)
    except Exception as e:
        print(f"[DATA] NSE option chain: {e}", file=sys.stderr)
    
    # Merge: prefer NSE, fallback to Yahoo
    if not option_chain_raw and yf_options:
        calls = {c["strike"]: c for c in yf_options.get("calls", [])}
        puts = {p["strike"]: p for p in yf_options.get("puts", [])}
        all_strikes = sorted(set(list(calls.keys()) + list(puts.keys())))
        for s in all_strikes:
            entry = {"strikePrice": s}
            c = calls.get(s, {})
            p = puts.get(s, {})
            if c:
                entry["CE"] = {
                    "openInterest": c.get("openInterest", 0) or 0,
                    "changeinOpenInterest": c.get("change", 0) or 0,
                    "lastPrice": c.get("lastPrice", 0) or 0,
                    "impliedVolatility": c.get("impliedVolatility", 0) or 0,
                    "totalTradedVolume": c.get("volume", 0) or 0,
                }
            if p:
                entry["PE"] = {
                    "openInterest": p.get("openInterest", 0) or 0,
                    "changeinOpenInterest": p.get("change", 0) or 0,
                    "lastPrice": p.get("lastPrice", 0) or 0,
                    "impliedVolatility": p.get("impliedVolatility", 0) or 0,
                    "totalTradedVolume": p.get("volume", 0) or 0,
                }
            option_chain_raw.append(entry)
    
    elapsed = round(time.time() - t0, 2)
    print(f"[DATA] Fetch complete in {elapsed}s", file=sys.stderr)
    
    return {
        "nifty": nifty_data,
        "vix": vix_data,
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "volumes": volumes,
        "vix_history": vix_history,
        "option_chain": option_chain_raw,
        "source": {
            "spot": "Yahoo Finance fast_info",
            "history": "Yahoo Finance download (6mo daily)",
            "options": "NSE" if option_chain_raw else ("Yahoo Finance" if yf_options else "none"),
        },
    }


# ─────────────── TECHNICAL HELPERS ───────────────

def ema(data, period):
    if len(data) < period:
        return None
    alpha = 2 / (period + 1)
    result = data[0]
    for val in data[1:]:
        result = alpha * val + (1 - alpha) * result
    return result


def sma(data, period):
    if len(data) < period:
        return None
    return sum(data[-period:]) / period


def rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i-1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def macd_full(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal:
        return [], [], []
    alpha_fast = 2 / (fast + 1)
    alpha_slow = 2 / (slow + 1)
    ema_fast_vals = [prices[0]]
    ema_slow_vals = [prices[0]]
    for p in prices[1:]:
        ema_fast_vals.append(alpha_fast * p + (1 - alpha_fast) * ema_fast_vals[-1])
        ema_slow_vals.append(alpha_slow * p + (1 - alpha_slow) * ema_slow_vals[-1])
    macd_vals = [f - s for f, s in zip(ema_fast_vals, ema_slow_vals)]
    alpha_sig = 2 / (signal + 1)
    signal_vals = [macd_vals[0]]
    for m in macd_vals[1:]:
        signal_vals.append(alpha_sig * m + (1 - alpha_sig) * signal_vals[-1])
    histogram = [m - s for m, s in zip(macd_vals, signal_vals)]
    return macd_vals, signal_vals, histogram


# ─────────────── PIPELINE ───────────────

def run_pipeline(raw):
    nf = raw["nifty"]
    vx = raw["vix"]
    closes = raw["closes"]
    highs = raw["highs"]
    lows = raw["lows"]
    vix_history = raw["vix_history"]
    chain = raw["option_chain"]
    
    spot = nf["spot"]
    vix_val = vx["vix"]
    
    # Day change
    prev = nf.get("prev_close")
    if spot and prev:
        change = round(spot - prev, 2)
        pct = round((change / prev) * 100, 2)
    else:
        change = 0
        pct = 0
    
    # ────────── 1. MARKET DATA ──────────
    print("[1/15] Market Data")
    mkt = {
        "spot": spot,
        "prev_close": prev,
        "open": nf.get("open"),
        "high": nf.get("high"),
        "low": nf.get("low"),
        "change": change,
        "pct_change": pct,
        "ema_50": round(nf.get("fifty_day_avg"), 2) if nf.get("fifty_day_avg") else None,
        "ema_200": round(nf.get("two_hundred_day_avg"), 2) if nf.get("two_hundred_day_avg") else None,
        "year_high": nf.get("year_high"),
        "year_low": nf.get("year_low"),
        "timestamp": datetime.now().isoformat(),
        "source": raw["source"]["spot"],
    }
    
    # ────────── 2. TREND ANALYSIS ──────────
    print("[2/15] Trend Analysis")
    
    ema_20 = ema(closes, 20)
    ema_50_calc = ema(closes, 50)
    ema_200_calc = ema(closes, 200)
    
    # ADX
    adx_val = None
    di_plus = None
    di_minus = None
    if len(closes) >= 15:
        recent_c = closes[-15:]
        recent_h = highs[-15:] if len(highs) >= 15 else closes[-15:]
        recent_l = lows[-15:] if len(lows) >= 15 else closes[-15:]
        dm_p, dm_m, trs = [], [], []
        for i in range(1, 15):
            trs.append(max(recent_h[i] - recent_l[i], abs(recent_h[i] - recent_c[i-1]), abs(recent_l[i] - recent_c[i-1])))
            dm_p.append(max(recent_h[i] - recent_h[i-1], 0))
            dm_m.append(max(recent_l[i-1] - recent_l[i], 0))
        atr14 = sum(trs) / len(trs) if trs else 1
        avg_dmp = sum(dm_p) / len(dm_p) if dm_p else 0
        avg_dmm = sum(dm_m) / len(dm_m) if dm_m else 0
        di_plus = round((avg_dmp / atr14) * 100, 1) if atr14 > 0 else 0
        di_minus = round((avg_dmm / atr14) * 100, 1) if atr14 > 0 else 0
        dx = abs(di_plus - di_minus) / max(di_plus + di_minus, 0.01) * 100
        adx_val = round(dx, 1)
    
    trend_dir = "bullish" if pct > 0.5 else ("bearish" if pct < -0.5 else "neutral")
    trend_str = "strong" if adx_val and adx_val > 25 else ("moderate" if adx_val and adx_val > 20 else "weak")
    
    day_h = nf.get("high") or spot
    day_l = nf.get("low") or spot
    range_pct = round(((day_h - day_l) / day_l) * 100, 2) if day_h and day_l and day_l > 0 else 0
    pos_range = round(((spot - day_l) / (day_h - day_l)) * 100, 1) if day_h != day_l else 50 if spot else None
    
    trend = {
        "direction": trend_dir,
        "strength": trend_str,
        "day_change_pct": pct,
        "day_range_pct": range_pct,
        "position_in_day_range_pct": pos_range,
        "ema_20": round(ema_20, 2) if ema_20 else None,
        "ema_50": round(ema_50_calc, 2) if ema_50_calc else None,
        "ema_200": round(ema_200_calc, 2) if ema_200_calc else None,
        "price_vs_ema_20": "above" if spot and ema_20 and spot > ema_20 else "below",
        "price_vs_ema_50": "above" if spot and ema_50_calc and spot > ema_50_calc else "below",
        "ema_20_50_cross": "golden_cross" if (ema_20 and ema_50_calc and ema_20 > ema_50_calc) else "death_cross",
        "adx": adx_val,
        "di_plus": di_plus,
        "di_minus": di_minus,
    }
    
    # ────────── 3. OPTION CHAIN ──────────
    print("[3/15] Option Chain")
    chain_summary = {
        "records": len(chain),
        "strike_range": None,
        "source": raw["source"]["options"],
    }
    if chain:
        strikes = [e.get("strikePrice", 0) for e in chain if e.get("strikePrice")]
        if strikes:
            chain_summary["strike_range"] = [min(strikes), max(strikes)]
            chain_summary["strike_count"] = len(set(strikes))
    
    # ────────── 4. OI + CHANGE IN OI ──────────
    print("[4/15] OI + Change in OI")
    tco, tpo, tco_chg, tpo_chg = 0, 0, 0, 0
    top_ce, top_pe = [], []
    
    if chain:
        for e in chain:
            s = e.get("strikePrice", 0)
            ce = e.get("CE", {})
            pe = e.get("PE", {})
            if ce:
                oi = ce.get("openInterest", 0) or 0
                oic = ce.get("changeinOpenInterest", 0) or 0
                tco += oi; tco_chg += oic
                top_ce.append({"strike": s, "oi": oi, "oi_change": oic, "ltp": ce.get("lastPrice"), "volume": ce.get("totalTradedVolume")})
            if pe:
                oi = pe.get("openInterest", 0) or 0
                oic = pe.get("changeinOpenInterest", 0) or 0
                tpo += oi; tpo_chg += oic
                top_pe.append({"strike": s, "oi": oi, "oi_change": oic, "ltp": pe.get("lastPrice"), "volume": pe.get("totalTradedVolume")})
        top_ce.sort(key=lambda x: x["oi"], reverse=True)
        top_pe.sort(key=lambda x: x["oi"], reverse=True)
    
    pcr_oi = round(tpo / tco, 3) if tco > 0 else None
    oi_sent = "bullish (low put OI)" if pcr_oi and pcr_oi < 0.7 else ("bearish (high put OI)" if pcr_oi and pcr_oi > 1.3 else "neutral")
    
    oi = {
        "total_call_oi": tco, "total_put_oi": tpo,
        "call_oi_change": tco_chg, "put_oi_change": tpo_chg,
        "pcr_oi": pcr_oi,
        "oi_sentiment": oi_sent,
        "call_oi_build": "aggressive" if tco_chg > tco * 0.05 and tco > 0 else ("unwinding" if tco_chg < 0 else "stable"),
        "put_oi_build": "aggressive" if tpo_chg > tpo * 0.05 and tpo > 0 else ("unwinding" if tpo_chg < 0 else "stable"),
        "top_call_oi": top_ce[:5],
        "top_put_oi": top_pe[:5],
    }
    
    # ────────── 5. IV + IV RANK ──────────
    print("[5/15] IV + IV Rank")
    atm_strike = round(spot / 50) * 50 if spot else None
    atm_iv = None
    all_ivs = []
    
    if chain and spot:
        for e in chain:
            s = e.get("strikePrice", 0)
            ce_iv = (e.get("CE", {}).get("impliedVolatility", 0) or 0)
            pe_iv = (e.get("PE", {}).get("impliedVolatility", 0) or 0)
            if ce_iv > 0: all_ivs.append(ce_iv)
            if pe_iv > 0: all_ivs.append(pe_iv)
            if s == atm_strike:
                atm_iv = ce_iv or pe_iv
    
    if not atm_iv and all_ivs:
        atm_iv = sum(all_ivs) / len(all_ivs)
    
    vix_pctl = None
    if vix_val and vix_history:
        vs = sorted(vix_history)
        vix_pctl = round(sum(1 for v in vs if v <= vix_val) / len(vs) * 100, 1)
    
    iv_mean = round(sum(all_ivs) / len(all_ivs), 2) if all_ivs else None
    iv_hi = round(max(all_ivs), 2) if all_ivs else None
    iv_lo = round(min(all_ivs), 2) if all_ivs else None
    
    iv_rank_chain = None
    if atm_iv and iv_hi and iv_lo and iv_hi != iv_lo:
        iv_rank_chain = round(((atm_iv - iv_lo) / (iv_hi - iv_lo)) * 100, 1)
    
    iv_reg = "high" if atm_iv and atm_iv > 20 else ("low" if atm_iv and atm_iv < 12 else "moderate") if atm_iv else "unknown"
    
    iv = {
        "atm_strike": atm_strike,
        "atm_iv": round(atm_iv, 2) if atm_iv else None,
        "iv_rank_chain_pct": iv_rank_chain,
        "vix_percentile_3mo": vix_pctl,
        "iv_mean": iv_mean, "iv_high": iv_hi, "iv_low": iv_lo,
        "iv_regime": iv_reg,
    }
    
    # ────────── 6. PCR ──────────
    print("[6/15] PCR")
    tcv, tpv = 0, 0
    if chain:
        for e in chain:
            ce_v = (e.get("CE", {}).get("totalTradedVolume", 0) or 0)
            pe_v = (e.get("PE", {}).get("totalTradedVolume", 0) or 0)
            tcv += ce_v; tpv += pe_v
    pcr_vol = round(tpv / tcv, 3) if tcv > 0 else None
    
    if pcr_oi and pcr_vol:
        if pcr_oi < 0.7 and pcr_vol < 0.7: pcr_int = "bullish — calls dominate"
        elif pcr_oi > 1.3 and pcr_vol > 1.3: pcr_int = "bearish — heavy put activity"
        elif pcr_oi < 1.0 < pcr_vol: pcr_int = "OI bull / vol bear divergence"
        elif pcr_oi > 1.0 > pcr_vol: pcr_int = "OI bear / vol bull divergence"
        else: pcr_int = "balanced"
    else:
        pcr_int = "insufficient data"
    
    pcr_out = {"pcr_oi": pcr_oi, "pcr_volume": pcr_vol, "total_call_vol": tcv, "total_put_vol": tpv, "interpretation": pcr_int}
    
    # ────────── 7. VOLUME ──────────
    print("[7/15] Volume")
    unusual = []
    if chain:
        for e in chain:
            s = e.get("strikePrice", 0)
            for typ in ["CE", "PE"]:
                d = e.get(typ, {})
                oi_v = d.get("openInterest", 0) or 0
                vol_v = d.get("totalTradedVolume", 0) or 0
                if oi_v > 0 and vol_v > 0:
                    ratio = vol_v / oi_v
                    if ratio > 1.5:
                        unusual.append({"type": typ, "strike": s, "volume": vol_v, "oi": oi_v, "vol_oi_ratio": round(ratio, 1), "ltp": d.get("lastPrice")})
    unusual.sort(key=lambda x: x["vol_oi_ratio"], reverse=True)
    
    vol = {
        "total_call_vol": tcv, "total_put_vol": tpv,
        "unusual_activity": unusual[:8],
        "sentiment": "call_driven" if pcr_vol and pcr_vol < 0.8 else ("put_driven" if pcr_vol and pcr_vol > 1.2 else "balanced"),
    }
    
    # ────────── 8. RSI + MACD ──────────
    print("[8/15] RSI + MACD")
    rsi14 = rsi(closes, 14)
    m_vals, s_vals, h_vals = macd_full(closes)
    
    rsi_v = round(rsi14, 1) if rsi14 else None
    macd_l = round(m_vals[-1], 2) if m_vals else None
    sig_l = round(s_vals[-1], 2) if s_vals else None
    hist_l = round(h_vals[-1], 2) if h_vals else None
    
    macd_cross = None
    if len(m_vals) >= 3 and len(s_vals) >= 3:
        if m_vals[-2] <= s_vals[-2] and m_vals[-1] > s_vals[-1]:
            macd_cross = "bullish_crossover"
        elif m_vals[-2] >= s_vals[-2] and m_vals[-1] < s_vals[-1]:
            macd_cross = "bearish_crossover"
        elif macd_l and sig_l:
            macd_cross = "above_signal" if macd_l > sig_l else "below_signal"
    
    rsi_int = "overbought" if rsi_v and rsi_v > 70 else ("oversold" if rsi_v and rsi_v < 30 else "neutral")
    
    tech = {
        "rsi_14": rsi_v,
        "rsi_interpretation": rsi_int,
        "macd_line": macd_l, "macd_signal": sig_l, "macd_histogram": hist_l,
        "macd_crossover": macd_cross,
        "data_points": len(closes),
    }
    
    # ────────── 9. SUPPORT / RESISTANCE ──────────
    print("[9/15] Support / Resistance")
    
    sw_hi = max(closes[-20:]) if len(closes) >= 20 else None
    sw_lo = min(closes[-20:]) if len(closes) >= 20 else None
    
    oi_res, oi_sup = [], []
    if spot and chain:
        for e in chain:
            s = e.get("strikePrice", 0)
            ce_oi = (e.get("CE", {}).get("openInterest", 0) or 0)
            pe_oi = (e.get("PE", {}).get("openInterest", 0) or 0)
            if s > spot and ce_oi: oi_res.append({"strike": s, "call_oi": ce_oi})
            if s < spot and pe_oi: oi_sup.append({"strike": s, "put_oi": pe_oi})
        oi_res.sort(key=lambda x: x["call_oi"], reverse=True)
        oi_sup.sort(key=lambda x: x["put_oi"], reverse=True)
    
    round_lvls = []
    if spot:
        base = math.floor(spot / 100) * 100
        for o in range(-500, 501, 100):
            lvl = base + o
            if lvl > 0:
                round_lvls.append({"level": lvl, "type": "resistance" if lvl > spot else ("support" if lvl < spot else "spot")})
    
    sr = {
        "spot": spot,
        "swing_high_20d": sw_hi, "swing_low_20d": sw_lo,
        "pivot_range": round(sw_hi - sw_lo, 2) if sw_hi and sw_lo else None,
        "oi_resistance": oi_res[:3],
        "oi_support": oi_sup[:3],
        "round_levels": round_lvls,
    }
    
    # ────────── 10. VIX ──────────
    print("[10/15] VIX")
    vix_chg = None
    vix_chg_pct = None
    if vix_val and vx.get("prev_close"):
        vix_chg = round(vix_val - vx["prev_close"], 2)
        vix_chg_pct = round((vix_chg / vx["prev_close"]) * 100, 2) if vx["prev_close"] != 0 else None
    
    vix_sma20 = sma(vix_history, 20)
    vix_sma50 = sma(vix_history, 50)
    
    if vix_val:
        if vix_val < 12: vr = "extremely_low — complacency"
        elif vix_val < 16: vr = "low — calm, seller's market"
        elif vix_val < 20: vr = "moderate — normal"
        elif vix_val < 25: vr = "elevated — caution"
        else: vr = "high — fear"
    else:
        vr = "unknown"
    
    vix_out = {
        "india_vix": vix_val,
        "change": vix_chg, "change_pct": vix_chg_pct,
        "day_high": vx.get("high"), "day_low": vx.get("low"),
        "percentile_3mo": vix_pctl,
        "sma_20": round(vix_sma20, 2) if vix_sma20 else None,
        "sma_50": round(vix_sma50, 2) if vix_sma50 else None,
        "regime": vr,
        "weekly_range_estimate": f"±{round(vix_val / math.sqrt(52), 2)}%" if vix_val else None,
    }
    
    # ────────── 11. EXPIRY / THETA ──────────
    print("[11/15] Expiry / Theta")
    try:
        exp_dt = datetime.strptime(EXPIRY_DATE_STR, "%Y-%m-%d")
        days_left = max(0, (exp_dt - datetime.now()).days)
        tdays = max(1, int(days_left * 5 / 7))
    except:
        days_left = tdays = 0
    
    if days_left > 15: tz, dtp = "slow decay", 0.3
    elif days_left > 7: tz, dtp = "moderate decay", 0.7
    elif days_left > 3: tz, dtp = "fast decay", 1.5
    elif days_left > 0: tz, dtp = "gamma zone — extreme theta", 3.0
    else: tz, dtp = "expired", 0
    
    exp = {
        "expiry_date": EXPIRY_DISPLAY,
        "calendar_days_left": days_left,
        "est_trading_days_left": tdays,
        "theta_zone": tz,
        "est_daily_theta_pct": dtp,
        "strategy_bias": "sell premium (theta on your side)" if 3 <= days_left <= 7 else (
            "buy options (time on your side)" if days_left > 15 else (
            "balanced" if days_left > 0 else "expired")),
    }
    
    # ────────── 12. MARKET REGIME ──────────
    print("[12/15] Market Regime")
    vol_reg = "high_vol" if vix_val and vix_val > 18 else "low_vol"
    dir_reg = "trending" if trend_dir != "neutral" and adx_val and adx_val > 20 else "ranging"
    
    regime_map = {
        ("high_vol", "trending"): {"label": "High Vol Trending", "desc": "Directional but volatile — trend-follow, buy breakouts", "strategy": "Call/put debit spreads, directional longs"},
        ("high_vol", "ranging"): {"label": "High Vol Ranging", "desc": "Wide swings — whipsaw risk", "strategy": "Iron condors (wide), ratio spreads"},
        ("low_vol", "trending"): {"label": "Low Vol Trending", "desc": "Steady drift — limited premium", "strategy": "Calendar/diagonal spreads, bull/bear spreads"},
        ("low_vol", "ranging"): {"label": "Low Vol Ranging", "desc": "Ideal for premium selling", "strategy": "Iron condors, short strangles, credit spreads"},
    }
    ri = regime_map.get((vol_reg, dir_reg), {"label": "Unclassified", "desc": "N/A", "strategy": "Stand aside"})
    
    regime = {
        "volatility_regime": vol_reg, "directional_regime": dir_reg,
        "vix_level": vix_val, "adx": adx_val,
        "classification": ri["label"], "description": ri["desc"],
        "recommended_strategy": ri["strategy"],
        "option_bias": "sell_premium" if vol_reg == "low_vol" and dir_reg == "ranging" else (
            "buy_options" if vol_reg == "high_vol" and dir_reg == "trending" and days_left > 7 else "defined_risk"),
    }
    
    # ────────── 13. RISK ENGINE ──────────
    print("[13/15] Risk Engine")
    ann_vol = (vix_val or 15) / 100
    day_vol = ann_vol / math.sqrt(252)
    per_vol = day_vol * math.sqrt(max(days_left, 1))
    em1 = round((spot or 0) * per_vol, 1)
    em1p = round(per_vol * 100, 2)
    
    var95 = round((spot or 0) * day_vol * 1.645, 1)
    var99 = round((spot or 0) * day_vol * 2.326, 1)
    
    # Max pain
    mp_strike, mp_oi_max = None, 0
    if chain:
        for e in chain:
            s = e.get("strikePrice", 0)
            combo = (e.get("CE", {}).get("openInterest", 0) or 0) + (e.get("PE", {}).get("openInterest", 0) or 0)
            if combo > mp_oi_max:
                mp_oi_max = combo; mp_strike = s
    
    risk = {
        "spot": spot,
        "annualized_vol_pct": round(ann_vol * 100, 2),
        "daily_vol_pct": round(day_vol * 100, 3),
        "expected_move_1sd": em1, "expected_move_1sd_pct": em1p,
        "expected_move_2sd": round(em1 * 2, 1) if em1 else None,
        "var_95_1day": var95, "var_99_1day": var99,
        "risk_per_lot_pts": round(em1 * LOT_SIZE / (spot or 1), 2) if em1 and spot else None,
        "max_pain_estimate": {"strike": mp_strike, "combined_oi": mp_oi_max},
        "position_sizing": f"≤2% capital per trade, ≤6% total portfolio risk | {em1p}% 1σ move over {days_left}d" if spot else None,
    }
    
    # ────────── 14. SCENARIO ANALYSIS ──────────
    print("[14/15] Scenario Analysis")
    bm = 1.15 if trend_dir == "bullish" else (0.85 if trend_dir == "bearish" else 1.0)
    bem = 0.85 if trend_dir == "bullish" else (1.15 if trend_dir == "bearish" else 1.0)
    
    bull_t = round((spot or 0) + em1 * bm, 1)
    bear_t = round((spot or 0) - em1 * bem, 1)
    base_u = round((spot or 0) + em1 * 0.3, 1)
    base_d = round((spot or 0) - em1 * 0.3, 1)
    
    scenario = {
        "spot": spot, "trend_bias": trend_dir,
        "scenarios": {
            "bull_case": {"target": bull_t, "move_pct": round(em1p * bm, 2), "probability": "~34%", "strategy": "Buy calls, bull call spreads, sell OTM puts", "key_resistances": [r["strike"] for r in oi_res[:2]]},
            "base_case": {"target_range": [base_d, base_u], "move_pct_range": [-round(em1p * 0.3, 2), round(em1p * 0.3, 2)], "probability": "~38%", "strategy": "Iron condor, short strangle, calendar spread"},
            "bear_case": {"target": bear_t, "move_pct": -round(em1p * bem, 2), "probability": "~34%", "strategy": "Buy puts, bear put spreads, sell OTM calls", "key_supports": [s["strike"] for s in oi_sup[:2]]},
            "tail_risk": {"target_range": [round((spot or 0) - em1 * 2, 1), round((spot or 0) + em1 * 2, 1)], "move_pct_range": [-round(em1p * 2, 2), round(em1p * 2, 2)], "probability": "~5%", "strategy": "Long straddle/strangle, long VIX, tail hedges"},
        },
        "assumptions": {"vix": vix_val, "trend": trend_dir, "expected_1sd": em1, "days_to_expiry": days_left},
    }
    
    # ────────── 15. EXECUTIVE SUMMARY ──────────
    print("[15/15] Executive Summary")
    summary = {
        "symbol": "NIFTY 50",
        "spot": spot,
        "change_pct": pct,
        "expiry": EXPIRY_DISPLAY,
        "days_to_expiry": days_left,
        "trend": f"{trend_dir} ({trend_str})",
        "adx": adx_val, "rsi_14": rsi_v,
        "macd_signal": macd_cross,
        "india_vix": vix_val, "vix_regime": vr,
        "pcr_oi": pcr_oi, "pcr_volume": pcr_vol,
        "atm_iv": round(atm_iv, 1) if atm_iv else None, "iv_regime": iv_reg,
        "oi_resistance_1": oi_res[0]["strike"] if oi_res else None,
        "oi_support_1": oi_sup[0]["strike"] if oi_sup else None,
        "max_pain_strike": mp_strike,
        "expected_1sd_move": f"±{em1p}% (±{em1} pts)" if em1 else None,
        "var_95_1d": var95,
        "market_regime": ri["label"],
        "theta_zone": tz,
        "preferred_strategy": ri["strategy"],
        "option_bias": "sell_premium" if vol_reg == "low_vol" and dir_reg == "ranging" else ("buy_options" if vol_reg == "high_vol" and dir_reg == "trending" else "defined_risk"),
    }
    
    # ────────── BUILD JSON ──────────
    output = {
        "meta": {
            "symbol": "NIFTY 50",
            "expiry": EXPIRY_DISPLAY, "lot_size": LOT_SIZE,
            "timestamp": datetime.now().isoformat(),
            "data_source": "Yahoo Finance + NSE",
            "disclaimer": "Educational/research only. Not financial advice.",
        },
        "1_market_data": mkt,
        "2_trend_analysis": trend,
        "3_option_chain": chain_summary,
        "4_oi_analysis": oi,
        "5_iv_analysis": iv,
        "6_pcr": pcr_out,
        "7_volume_profile": vol,
        "8_rsi_macd": tech,
        "9_support_resistance": sr,
        "10_vix": vix_out,
        "11_expiry_theta": exp,
        "12_market_regime": regime,
        "13_risk_engine": risk,
        "14_scenario_analysis": scenario,
        "15_executive_summary": summary,
    }
    
    return output


# ─────────────── MAIN ───────────────

def main():
    print("=" * 60)
    print("  NIFTY 50 OPTIONS ANALYSIS — FULL PIPELINE")
    print(f"  Expiry: {EXPIRY_DISPLAY} | Lot: {LOT_SIZE}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=" * 60)
    print()
    
    raw = fetch_all_raw()
    
    if not raw["nifty"]["spot"]:
        output = {"error": "Failed to fetch Nifty spot", "timestamp": datetime.now().isoformat()}
    else:
        output = run_pipeline(raw)
    
    print("\n" + "=" * 60)
    print(json.dumps(output, indent=2, default=str))
    
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)) or ".",
                            "nifty_analysis_output.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n✅ Saved: {out_path}")
    
    return output


if __name__ == "__main__":
    main()
