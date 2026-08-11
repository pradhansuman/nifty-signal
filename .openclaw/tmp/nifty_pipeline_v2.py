#!/usr/bin/env python3
"""
Nifty 50 Options Analysis Pipeline v2 — 15-step with CSV import + tuned regime engine
======================================================================================
Data: Yahoo Finance (spot, VIX, technicals) + CSV option chain import

CSV format (NSE download or export):
  strike,ce_ltp,ce_oi,ce_oi_chg,ce_vol,ce_iv,pe_ltp,pe_oi,pe_oi_chg,pe_vol,pe_iv
  (header row expected; all numeric except header)
"""

import json, math, sys, os, csv, io
from datetime import datetime, timedelta
from collections import defaultdict, deque
import time, warnings
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

OPTION_CHAIN_CSV = None  # Set to path, or pass via --chain-csv

# ─────────────── DATA FETCH ───────────────

def fetch_yahoo_data():
    t0 = time.time()
    nifty = yf.Ticker(SYMBOL)
    vix_t = yf.Ticker(VIX_SYMBOL)
    
    # Spot data (snake_case)
    nf = nifty.fast_info
    spot = getattr(nf, "last_price", None)
    if not spot:
        spot = (nifty.info or {}).get("regularMarketPrice")
    
    nifty_data = {
        "spot": spot,
        "prev_close": getattr(nf, "previous_close", None) or getattr(nf, "regular_market_previous_close", None),
        "open": getattr(nf, "open", None),
        "high": getattr(nf, "day_high", None),
        "low": getattr(nf, "day_low", None),
        "ema_50": getattr(nf, "fifty_day_average", None),
        "ema_200": getattr(nf, "two_hundred_day_average", None),
        "year_high": getattr(nf, "year_high", None),
        "year_low": getattr(nf, "year_low", None),
    }
    
    vf = vix_t.fast_info
    vix_val = getattr(vf, "last_price", None)
    vix_data = {
        "vix": vix_val,
        "prev_close": getattr(vf, "previous_close", None) or getattr(vf, "regular_market_previous_close", None),
        "high": getattr(vf, "day_high", None),
        "low": getattr(vf, "day_low", None),
    }
    
    # Historical: 1 year for proper VIX percentile
    print("[DATA] Fetching 1-year history + 6-month VIX...", file=sys.stderr)
    hist = yf.download(SYMBOL, period="1y", interval="1d", progress=False, auto_adjust=False)
    if isinstance(hist.columns, pd.MultiIndex):
        cc = ("Close", SYMBOL) if ("Close", SYMBOL) in hist.columns else hist.columns[0]
        hc = ("High", SYMBOL) if ("High", SYMBOL) in hist.columns else None
        lc = ("Low", SYMBOL) if ("Low", SYMBOL) in hist.columns else None
    else:
        cc, hc, lc = "Close", "High", "Low"
    
    closes = pd.Series(hist[cc]).dropna().values.tolist()
    highs = pd.Series(hist[hc]).dropna().values.tolist() if hc else closes
    lows = pd.Series(hist[lc]).dropna().values.tolist() if lc else closes
    
    # VIX: 6 months
    vix_hist = yf.download(VIX_SYMBOL, period="6mo", interval="1d", progress=False, auto_adjust=False)
    if isinstance(vix_hist.columns, pd.MultiIndex):
        vc = ("Close", VIX_SYMBOL) if ("Close", VIX_SYMBOL) in vix_hist.columns else vix_hist.columns[0]
    else:
        vc = "Close"
    vix_history = pd.Series(vix_hist[vc]).dropna().values.tolist()
    
    elapsed = round(time.time() - t0, 2)
    print(f"[DATA] Fetch complete in {elapsed}s | {len(closes)} price bars, {len(vix_history)} VIX bars", file=sys.stderr)
    
    return {
        "nifty": nifty_data,
        "vix": vix_data,
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "vix_history": vix_history,
    }


def load_option_chain_csv(path):
    """Load option chain from CSV file.
    Expected columns: strike, ce_ltp, ce_oi, ce_oi_chg, ce_vol, ce_iv, pe_ltp, pe_oi, pe_oi_chg, pe_vol, pe_iv
    Also accepts NSE bhavcopy format with auto-detection.
    """
    if not path or not os.path.exists(path):
        return []
    
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        chain = []
        for row in reader:
            # Try multiple column name formats
            strike = float(row.get("strike", row.get("strikePrice", row.get("STRIKE_PRICE", 0))) or 0)
            if not strike:
                continue
            
            entry = {"strikePrice": strike}
            
            # CE data
            ce_oi = float(row.get("ce_oi", row.get("CE_OPEN_INTEREST", row.get("call_open_interest", 0))) or 0)
            ce_oi_chg = float(row.get("ce_oi_chg", row.get("CE_CHG_IN_OI", row.get("call_oi_change", 0))) or 0)
            ce_ltp = float(row.get("ce_ltp", row.get("CE_LAST_PRICE", row.get("call_ltp", 0))) or 0)
            ce_vol = float(row.get("ce_vol", row.get("CE_VOLUME", row.get("call_volume", 0))) or 0)
            ce_iv = float(row.get("ce_iv", row.get("CE_IMPLIED_VOLATILITY", row.get("call_iv", 0))) or 0)
            
            if ce_oi or ce_ltp:
                entry["CE"] = {
                    "openInterest": ce_oi,
                    "changeinOpenInterest": ce_oi_chg,
                    "lastPrice": ce_ltp,
                    "totalTradedVolume": ce_vol,
                    "impliedVolatility": ce_iv,
                }
            
            # PE data
            pe_oi = float(row.get("pe_oi", row.get("PE_OPEN_INTEREST", row.get("put_open_interest", 0))) or 0)
            pe_oi_chg = float(row.get("pe_oi_chg", row.get("PE_CHG_IN_OI", row.get("put_oi_change", 0))) or 0)
            pe_ltp = float(row.get("pe_ltp", row.get("PE_LAST_PRICE", row.get("put_ltp", 0))) or 0)
            pe_vol = float(row.get("pe_vol", row.get("PE_VOLUME", row.get("put_volume", 0))) or 0)
            pe_iv = float(row.get("pe_iv", row.get("PE_IMPLIED_VOLATILITY", row.get("put_iv", 0))) or 0)
            
            if pe_oi or pe_ltp:
                entry["PE"] = {
                    "openInterest": pe_oi,
                    "changeinOpenInterest": pe_oi_chg,
                    "lastPrice": pe_ltp,
                    "totalTradedVolume": pe_vol,
                    "impliedVolatility": pe_iv,
                }
            
            chain.append(entry)
        
        print(f"[CSV] Loaded {len(chain)} strikes from {path}", file=sys.stderr)
        return chain


# ─────────────── TECHNICALS ───────────────

def ema(data, period):
    if len(data) < period: return None
    alpha = 2 / (period + 1)
    result = data[0]
    for v in data[1:]: result = alpha * v + (1 - alpha) * result
    return result

def sma(data, period):
    if len(data) < period: return None
    return sum(data[-period:]) / period

def rsi(prices, period=14):
    if len(prices) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains[:period]) / period; al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period-1) + gains[i]) / period
        al = (al * (period-1) + losses[i]) / period
    if al == 0: return 100.0
    return 100 - (100 / (1 + ag / al))

def macd_full(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal: return [], [], []
    af, asl = 2/(fast+1), 2/(slow+1)
    ef, esl = [prices[0]], [prices[0]]
    for p in prices[1:]:
        ef.append(af*p + (1-af)*ef[-1])
        esl.append(asl*p + (1-asl)*esl[-1])
    mv = [f-s for f,s in zip(ef, esl)]
    asi = 2/(signal+1)
    sv = [mv[0]]
    for m in mv[1:]: sv.append(asi*m + (1-asi)*sv[-1])
    return mv, sv, [m-s for m,s in zip(mv, sv)]

def atr_func(highs, lows, closes, period=14):
    if len(closes) < period+1: return None
    trs = []
    for i in range(1, len(closes)):
        h = highs[i] if i < len(highs) else closes[i]
        l = lows[i] if i < len(lows) else closes[i]
        trs.append(max(h-l, abs(h-closes[i-1]), abs(l-closes[i-1])))
    atr_v = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr_v = (atr_v*(period-1) + trs[i]) / period
    return atr_v

def percentile(values, target):
    """Where does target sit in sorted values? 0-100."""
    if not values or target is None: return None
    s = sorted(values)
    return round(sum(1 for v in s if v <= target) / len(s) * 100, 1)

def rolling_percentile_rank(values, window=20):
    """Compute rolling percentile rank of each point vs last 'window' values."""
    if len(values) < window: return []
    result = []
    buf = deque(values[:window])
    for i in range(window, len(values)):
        result.append(percentile(list(buf), values[i]))
        buf.popleft()
        buf.append(values[i])
    return result


# ─────────────── REGIME ENGINE (TUNED) ───────────────

def classify_regime(vix_val, vix_history, adx, trend_dir, closes, atr_current, atr_20d_ago):
    """Multi-factor regime classification with transition detection."""
    
    # ── Volatility dimension: VIX percentile + ATR expansion ──
    vix_pctl_6m = percentile(vix_history, vix_val)
    vix_pctl_1y = percentile(vix_history[-250:] if len(vix_history) > 250 else vix_history, vix_val)
    
    # ATR expansion/contraction
    atr_expanding = atr_current and atr_20d_ago and atr_current > atr_20d_ago * 1.1
    atr_contracting = atr_current and atr_20d_ago and atr_current < atr_20d_ago * 0.9
    
    # Volatility regime (3-tier)
    if vix_val:
        if vix_pctl_6m and vix_pctl_6m > 80:
            vol_tier = "extreme_high"
        elif vix_val > 20 or (vix_pctl_6m and vix_pctl_6m > 60):
            vol_tier = "high"
        elif vix_val > 14:
            vol_tier = "moderate"
        else:
            vol_tier = "low"
    else:
        vol_tier = "unknown"
    
    # ── Directional dimension: ADX + price vs key MAs ──
    if adx and adx > 30:
        dir_tier = "strong_trending"
    elif adx and adx > 20:
        dir_tier = "trending"
    elif adx and adx > 15:
        dir_tier = "weakly_trending" if trend_dir != "neutral" else "ranging"
    else:
        dir_tier = "ranging"
    
    # ── Regime transition detection ──
    # Check if ADX has crossed 20 in last 5 days
    transition = "stable"
    if len(closes) >= 25:
        # Simplified: check if recent ADX (approx from last 14 bars) is rising
        # We already have the current ADX; check trend direction consistency
        if trend_dir != "neutral" and dir_tier in ("trending", "strong_trending"):
            transition = "trend_strengthening" if atr_expanding else "trend_established"
        elif trend_dir == "neutral" and dir_tier == "ranging":
            transition = "consolidation" if atr_contracting else "range_bound"
        elif trend_dir != "neutral" and dir_tier == "ranging":
            transition = "potential_breakout"
    
    # ── Regime matrix (3 vol × 4 dir) ──
    regime_map = {
        ("low", "ranging"): {
            "label": "Low Vol Ranging",
            "desc": "Ideal premium-selling environment — collect theta with confidence",
            "strategy": "Iron condors, short strangles, credit spreads, naked puts",
            "confidence": "high",
        },
        ("low", "weakly_trending"): {
            "label": "Low Vol Drift",
            "desc": "Slow grind — limited premium, favor calendars and diagonals",
            "strategy": "Calendar spreads, put credit spreads, covered calls",
            "confidence": "moderate",
        },
        ("low", "trending"): {
            "label": "Low Vol Trending",
            "desc": "Steady directional move on low vol — rare and powerful",
            "strategy": "Bull/bear call spreads, directional debit spreads",
            "confidence": "high",
        },
        ("low", "strong_trending"): {
            "label": "Low Vol Breakout",
            "desc": "Strong trend with low vol compression — breakout territory",
            "strategy": "Long calls/puts, ratio spreads, avoid premium selling",
            "confidence": "high",
        },
        ("moderate", "ranging"): {
            "label": "Moderate Vol Ranging",
            "desc": "Balanced — premium selling works but keep wings wide",
            "strategy": "Iron condors (wider), credit spreads, short strangles (small)",
            "confidence": "moderate",
        },
        ("moderate", "weakly_trending"): {
            "label": "Moderate Vol Drift",
            "desc": "Directional bias with moderate premium — balanced approach",
            "strategy": "Put/call credit spreads leaning directional, diagonals",
            "confidence": "moderate",
        },
        ("moderate", "trending"): {
            "label": "Moderate Vol Trending",
            "desc": "Clean trend with decent premium — directional strategies",
            "strategy": "Debit spreads, butterflies at target, avoid naked shorts",
            "confidence": "high",
        },
        ("moderate", "strong_trending"): {
            "label": "Volatile Trend",
            "desc": "Strong directional with elevated vol — trend-follow",
            "strategy": "Call/put debit spreads, ratio spreads, trailing stops",
            "confidence": "high",
        },
        ("high", "ranging"): {
            "label": "High Vol Ranging",
            "desc": "Wide swings, whipsaw risk — defined risk essential",
            "strategy": "Iron condors (very wide), ratio spreads, small size only",
            "confidence": "low",
        },
        ("high", "weakly_trending"): {
            "label": "High Vol Drift",
            "desc": "Elevated vol with mild direction — expensive premiums",
            "strategy": "Vertical spreads (debit), calendars — avoid naked selling",
            "confidence": "low",
        },
        ("high", "trending"): {
            "label": "High Vol Trending",
            "desc": "Large directional moves — trend-following, buy breakouts",
            "strategy": "Call/put debit spreads, directional longs, avoid short gamma",
            "confidence": "moderate",
        },
        ("high", "strong_trending"): {
            "label": "Extreme Vol Trending",
            "desc": "Very strong trend + high vol — momentum regime",
            "strategy": "Long calls/puts, wide debit spreads, strict stop losses",
            "confidence": "moderate",
        },
        ("extreme_high", "ranging"): {
            "label": "Crisis Ranging",
            "desc": "Extreme fear with no clear direction — stand aside or hedge",
            "strategy": "Long straddles, VIX hedges, minimal position size",
            "confidence": "low",
        },
        ("extreme_high", "strong_trending"): {
            "label": "Crash / Melt-Up",
            "desc": "Extreme directional panic — trend is your only friend",
            "strategy": "Long options (momentum), avoid selling, tight stops",
            "confidence": "moderate",
        },
    }
    
    key = (vol_tier, dir_tier)
    ri = regime_map.get(key, {"label": f"{vol_tier}/{dir_tier}", "desc": "Unclassified", "strategy": "Stand aside or use minimal positions", "confidence": "low"})
    
    return {
        "volatility_tier": vol_tier,
        "directional_tier": dir_tier,
        "vix_percentile_6m": vix_pctl_6m,
        "vix_percentile_1y": vix_pctl_1y,
        "atr_expanding": atr_expanding,
        "atr_contracting": atr_contracting,
        "transition_state": transition,
        **ri,
        "option_bias": (
            "sell_premium" if vol_tier in ("low", "moderate") and dir_tier == "ranging"
            else "buy_directional" if vol_tier in ("high", "extreme_high") and dir_tier in ("trending", "strong_trending")
            else "defined_risk"
        ),
    }


# ─────────────── SCENARIO WEIGHTS (TUNED) ───────────────

def compute_scenario_weights(trend_dir, trend_str, vix_val, vix_pctl, days_left, adx, rsi_val):
    """Compute probability-weighted scenarios with dynamic adjustment."""
    
    # Base probabilities
    base = {"bull": 0.34, "base": 0.38, "bear": 0.34, "tail": 0.05}
    
    # ── Trend adjustment ──
    trend_bull_mult = 1.0
    trend_bear_mult = 1.0
    
    if trend_dir == "bullish":
        if trend_str in ("strong",):
            trend_bull_mult = 1.4; trend_bear_mult = 0.6
        else:
            trend_bull_mult = 1.2; trend_bear_mult = 0.8
    elif trend_dir == "bearish":
        if trend_str in ("strong",):
            trend_bull_mult = 0.6; trend_bear_mult = 1.4
        else:
            trend_bull_mult = 0.8; trend_bear_mult = 1.2
    
    # ── VIX adjustment ──
    # Low VIX → fatter tails (compression → expansion)
    # High VIX → wider expected moves already priced in
    vix_tail_mult = 1.0
    if vix_val:
        if vix_val < 12: vix_tail_mult = 1.5  # Very low VIX → tail risk higher
        elif vix_val < 15: vix_tail_mult = 1.2
        elif vix_val > 25: vix_tail_mult = 0.8  # High VIX → tails already wide
    
    # ── RSI adjustment ──
    # Overbought → bear case more likely; oversold → bull case more likely
    rsi_bull_mult = 1.0; rsi_bear_mult = 1.0
    if rsi_val:
        if rsi_val > 70: rsi_bull_mult = 0.7; rsi_bear_mult = 1.3
        elif rsi_val > 60: rsi_bull_mult = 0.9; rsi_bear_mult = 1.1
        elif rsi_val < 30: rsi_bull_mult = 1.3; rsi_bear_mult = 0.7
        elif rsi_val < 40: rsi_bull_mult = 1.1; rsi_bear_mult = 0.9
    
    # ── Days-to-expiry adjustment ──
    # Closer to expiry → more mean-reversion (base case probability higher)
    expiry_base_mult = 1.0
    if days_left <= 3: expiry_base_mult = 1.3
    elif days_left <= 7: expiry_base_mult = 1.15
    
    # ── Compute weighted probabilities ──
    w_bull = base["bull"] * trend_bull_mult * rsi_bull_mult
    w_bear = base["bear"] * trend_bear_mult * rsi_bear_mult
    w_base = base["base"] * expiry_base_mult
    w_tail = base["tail"] * vix_tail_mult
    
    # Normalize
    total = w_bull + w_base + w_bear + w_tail
    probabilities = {
        "bull": round(w_bull / total * 100, 1),
        "base": round(w_base / total * 100, 1),
        "bear": round(w_bear / total * 100, 1),
        "tail": round(w_tail / total * 100, 1),
    }
    
    # Adjustments used
    adjustments = {
        "trend_bias": trend_dir,
        "trend_multipliers": {"bull": trend_bull_mult, "bear": trend_bear_mult},
        "vix_tail_mult": vix_tail_mult,
        "rsi_multipliers": {"bull": rsi_bull_mult, "bear": rsi_bear_mult},
        "expiry_base_mult": expiry_base_mult,
        "vix_level": vix_val,
        "adx": adx,
    }
    
    return probabilities, adjustments


# ─────────────── MAIN PIPELINE ───────────────

def run_pipeline(raw, chain, expiry_str=None, expiry_display=None):
    nf = raw["nifty"]; vx = raw["vix"]
    closes = raw["closes"]; highs = raw["highs"]; lows = raw["lows"]
    vix_history = raw["vix_history"]
    
    # Use provided expiry or module defaults
    exp_str = expiry_str or EXPIRY_DATE_STR
    exp_disp = expiry_display or EXPIRY_DISPLAY
    
    spot = nf["spot"]; vix_val = vx["vix"]
    prev = nf.get("prev_close")
    pct = round((spot - prev) / prev * 100, 2) if spot and prev else 0
    
    # ── 1. MARKET DATA ──
    print("[1/15] Market Data")
    mkt = {
        "spot": spot, "prev_close": prev, "open": nf.get("open"),
        "high": nf.get("high"), "low": nf.get("low"),
        "change_pct": pct,
        "ema_50": round(nf.get("ema_50"), 2) if nf.get("ema_50") else None,
        "ema_200": round(nf.get("ema_200"), 2) if nf.get("ema_200") else None,
        "year_high": nf.get("year_high"), "year_low": nf.get("year_low"),
        "timestamp": datetime.now().isoformat(),
    }
    
    # ── 2. TREND ──
    print("[2/15] Trend Analysis")
    ema_20 = ema(closes, 20); ema_50c = ema(closes, 50)
    ema_200c = ema(closes, 200) if len(closes) >= 200 else None
    
    # ADX (14-period)
    adx_val = di_plus = di_minus = None
    if len(closes) >= 15:
        rc, rh, rl = closes[-15:], highs[-15:], lows[-15:]
        dmp, dmm, trs = [], [], []
        for i in range(1, 15):
            trs.append(max(rh[i]-rl[i], abs(rh[i]-rc[i-1]), abs(rl[i]-rc[i-1])))
            dmp.append(max(rh[i]-rh[i-1], 0))
            dmm.append(max(rl[i-1]-rl[i], 0))
        a14 = sum(trs)/len(trs) if trs else 1
        admp = sum(dmp)/len(dmp) if dmp else 0
        admm = sum(dmm)/len(dmm) if dmm else 0
        di_plus = round(admp/a14*100, 1) if a14>0 else 0
        di_minus = round(admm/a14*100, 1) if a14>0 else 0
        adx_val = round(abs(di_plus-di_minus)/max(di_plus+di_minus,0.01)*100, 1)
    
    # ATR
    atr_now = atr_func(highs, lows, closes, 14)
    atr_20d = atr_func(highs[:-20] if len(highs)>20 else highs, lows[:-20] if len(lows)>20 else lows, closes[:-20] if len(closes)>20 else closes, 14)
    
    trend_dir = "bullish" if pct > 0.3 else ("bearish" if pct < -0.3 else "neutral")
    trend_str = "strong" if adx_val and adx_val > 25 else ("moderate" if adx_val and adx_val > 20 else "weak")
    
    day_h, day_l = nf.get("high") or spot, nf.get("low") or spot
    range_pct = round(((day_h-day_l)/day_l)*100, 2) if day_h and day_l and day_l>0 else 0
    pos_range = round(((spot-day_l)/(day_h-day_l))*100, 1) if spot and day_h!=day_l else 50
    
    trend = {
        "direction": trend_dir, "strength": trend_str,
        "day_change_pct": pct, "day_range_pct": range_pct,
        "position_in_day_range_pct": pos_range,
        "ema_20": round(ema_20,2) if ema_20 else None,
        "ema_50": round(ema_50c,2) if ema_50c else None,
        "ema_200": round(ema_200c,2) if ema_200c else None,
        "price_vs_ema_20": "above" if spot and ema_20 and spot>ema_20 else "below",
        "price_vs_ema_50": "above" if spot and ema_50c and spot>ema_50c else "below",
        "price_vs_ema_200": "above" if spot and ema_200c and spot>ema_200c else "below",
        "ema_20_50_cross": "golden_cross" if ema_20 and ema_50c and ema_20>ema_50c else "death_cross",
        "adx": adx_val, "di_plus": di_plus, "di_minus": di_minus,
        "atr": round(atr_now,2) if atr_now else None,
        "atr_vs_20d": "expanding" if atr_now and atr_20d and atr_now>atr_20d*1.05 else ("contracting" if atr_now and atr_20d and atr_now<atr_20d*0.95 else "stable"),
    }
    
    # ── 3. OPTION CHAIN ──
    print("[3/15] Option Chain")
    chain_src = "CSV import" if chain else "none (supply --chain-csv)"
    chain_strikes = sorted(set(e.get("strikePrice", 0) for e in chain)) if chain else []
    chain_s = {
        "records": len(chain),
        "strike_range": [min(chain_strikes), max(chain_strikes)] if chain_strikes else None,
        "source": chain_src,
    }
    
    # ── 4. OI ──
    print("[4/15] OI + Change")
    tco = tpo = tco_chg = tpo_chg = 0
    top_ce, top_pe = [], []
    
    if chain:
        for e in chain:
            s = e["strikePrice"]; ce=e.get("CE",{}); pe=e.get("PE",{})
            if ce:
                oi=ce.get("openInterest",0)or 0; oic=ce.get("changeinOpenInterest",0)or 0
                tco+=oi; tco_chg+=oic
                top_ce.append({"strike":s,"oi":oi,"oi_change":oic,"ltp":ce.get("lastPrice"),"volume":ce.get("totalTradedVolume")})
            if pe:
                oi=pe.get("openInterest",0)or 0; oic=pe.get("changeinOpenInterest",0)or 0
                tpo+=oi; tpo_chg+=oic
                top_pe.append({"strike":s,"oi":oi,"oi_change":oic,"ltp":pe.get("lastPrice"),"volume":pe.get("totalTradedVolume")})
        top_ce.sort(key=lambda x:x["oi"], reverse=True); top_pe.sort(key=lambda x:x["oi"], reverse=True)
    
    pcr_oi = round(tpo/tco, 3) if tco>0 else None
    oi = {
        "total_call_oi": tco, "total_put_oi": tpo,
        "call_oi_change": tco_chg, "put_oi_change": tpo_chg,
        "pcr_oi": pcr_oi,
        "sentiment": "bullish" if pcr_oi and pcr_oi<0.7 else ("bearish" if pcr_oi and pcr_oi>1.3 else "neutral"),
        "call_oi_trend": "building" if tco_chg>0 else "unwinding",
        "put_oi_trend": "building" if tpo_chg>0 else "unwinding",
        "top_call_oi": top_ce[:5], "top_put_oi": top_pe[:5],
    }
    
    # ── 5. IV ──
    print("[5/15] IV + IV Rank")
    atm_strike = round(spot/50)*50 if spot else None
    atm_iv = None; all_ivs = []
    if chain and spot:
        for e in chain:
            s = e["strikePrice"]
            for k in ["CE","PE"]:
                iv = (e.get(k,{}).get("impliedVolatility",0) or 0)
                if iv>0: all_ivs.append(iv)
                if s==atm_strike and not atm_iv: atm_iv=iv
    if not atm_iv and all_ivs: atm_iv = sum(all_ivs)/len(all_ivs)
    
    vix_pctl_6m = percentile(vix_history, vix_val)
    
    iv = {
        "atm_strike": atm_strike,
        "atm_iv": round(atm_iv,2) if atm_iv else None,
        "iv_mean": round(sum(all_ivs)/len(all_ivs),2) if all_ivs else None,
        "iv_high": round(max(all_ivs),2) if all_ivs else None,
        "iv_low": round(min(all_ivs),2) if all_ivs else None,
        "vix_percentile_6m": vix_pctl_6m,
        "iv_regime": "high" if atm_iv and atm_iv>20 else ("low" if atm_iv and atm_iv<12 else "moderate") if atm_iv else "unknown",
    }
    
    # ── 6. PCR ──
    print("[6/15] PCR")
    tcv, tpv = 0, 0
    if chain:
        for e in chain:
            tcv += (e.get("CE",{}).get("totalTradedVolume",0)or 0)
            tpv += (e.get("PE",{}).get("totalTradedVolume",0)or 0)
    pcr_vol = round(tpv/tcv,3) if tcv>0 else None
    pcr_out = {"pcr_oi":pcr_oi,"pcr_volume":pcr_vol,"total_call_vol":tcv,"total_put_vol":tpv}
    
    # ── 7. VOLUME ──
    print("[7/15] Volume")
    unusual = []
    if chain:
        for e in chain:
            s = e["strikePrice"]
            for t in ["CE","PE"]:
                d = e.get(t,{}); oiv=d.get("openInterest",0)or 0; vv=d.get("totalTradedVolume",0)or 0
                if oiv>0 and vv>0:
                    r = vv/oiv
                    if r>1.5: unusual.append({"type":t,"strike":s,"volume":vv,"oi":oiv,"vol_oi_ratio":round(r,1),"ltp":d.get("lastPrice")})
    unusual.sort(key=lambda x:x["vol_oi_ratio"], reverse=True)
    vol = {"total_call_vol":tcv,"total_put_vol":tpv,"unusual_activity":unusual[:8],
           "sentiment":"call_driven" if pcr_vol and pcr_vol<0.8 else ("put_driven" if pcr_vol and pcr_vol>1.2 else "balanced")}
    
    # ── 8. RSI + MACD ──
    print("[8/15] RSI + MACD")
    rsi14 = rsi(closes, 14)
    m_vals, s_vals, h_vals = macd_full(closes)
    
    rsi_v = round(rsi14,1) if rsi14 else None
    macd_l = round(m_vals[-1],2) if m_vals else None
    sig_l = round(s_vals[-1],2) if s_vals else None
    hist_l = round(h_vals[-1],2) if h_vals else None
    
    macd_cross = None
    if len(m_vals)>=3:
        if m_vals[-2]<=s_vals[-2] and m_vals[-1]>s_vals[-1]: macd_cross="bullish_crossover"
        elif m_vals[-2]>=s_vals[-2] and m_vals[-1]<s_vals[-1]: macd_cross="bearish_crossover"
        elif macd_l and sig_l: macd_cross = "above_signal" if macd_l>sig_l else "below_signal"
    
    tech = {
        "rsi_14": rsi_v,
        "rsi_zone": "overbought" if rsi_v and rsi_v>70 else ("oversold" if rsi_v and rsi_v<30 else "neutral"),
        "macd_line": macd_l, "macd_signal": sig_l, "macd_histogram": hist_l,
        "macd_crossover": macd_cross,
        "data_points": len(closes),
    }
    
    # ── 9. S/R ──
    print("[9/15] Support/Resistance")
    sw_hi = max(closes[-20:]) if len(closes)>=20 else None
    sw_lo = min(closes[-20:]) if len(closes)>=20 else None
    
    oi_res, oi_sup = [], []
    if spot and chain:
        for e in chain:
            s = e["strikePrice"]
            ce_oi = (e.get("CE",{}).get("openInterest",0)or 0)
            pe_oi = (e.get("PE",{}).get("openInterest",0)or 0)
            if s>spot and ce_oi: oi_res.append({"strike":s,"call_oi":ce_oi})
            if s<spot and pe_oi: oi_sup.append({"strike":s,"put_oi":pe_oi})
        oi_res.sort(key=lambda x:x["call_oi"], reverse=True)
        oi_sup.sort(key=lambda x:x["put_oi"], reverse=True)
    
    round_lvls = []
    if spot:
        base = math.floor(spot/100)*100
        for o in range(-500,501,100):
            l=base+o
            if l>0: round_lvls.append({"level":l,"type":"resistance" if l>spot else ("support" if l<spot else "spot")})
    
    sr = {"spot":spot,"swing_high_20d":sw_hi,"swing_low_20d":sw_lo,
          "oi_resistance":oi_res[:3],"oi_support":oi_sup[:3],"round_levels":round_lvls}
    
    # ── 10. VIX ──
    print("[10/15] VIX")
    vix_chg = round(vix_val - vx["prev_close"],2) if vix_val and vx.get("prev_close") else None
    vix_chg_pct = round(vix_chg/vx["prev_close"]*100,2) if vix_chg is not None and vx.get("prev_close") and vx["prev_close"]!=0 else None
    
    vix_sma20 = sma(vix_history, 20); vix_sma50 = sma(vix_history, 50)
    
    if vix_val:
        if vix_val<12: vr="extremely_low — complacency"
        elif vix_val<16: vr="low — calm, seller's market"
        elif vix_val<20: vr="moderate — normal"
        elif vix_val<25: vr="elevated — caution"
        else: vr="high — fear"
    else: vr="unknown"
    
    vix_out = {
        "india_vix": vix_val, "change": vix_chg, "change_pct": vix_chg_pct,
        "day_high": vx.get("high"), "day_low": vx.get("low"),
        "percentile_6m": vix_pctl_6m,
        "sma_20": round(vix_sma20,2) if vix_sma20 else None,
        "sma_50": round(vix_sma50,2) if vix_sma50 else None,
        "regime": vr,
        "weekly_estimate": f"±{round(vix_val/math.sqrt(52),2)}%" if vix_val else None,
    }
    
    # ── 11. EXPIRY / THETA ──
    print("[11/15] Expiry/Theta")
    try:
        exp_dt = datetime.strptime(exp_str,"%Y-%m-%d")
        days_left = max(0,(exp_dt-datetime.now()).days)
        tdays = max(1,int(days_left*5/7))
    except: days_left=tdays=0
    
    if days_left>15: tz,dtp = "slow decay zone",0.3
    elif days_left>7: tz,dtp = "moderate decay",0.7
    elif days_left>3: tz,dtp = "fast decay — gamma building",1.5
    elif days_left>0: tz,dtp = "gamma zone — extreme theta, avoid naked shorts",3.0
    else: tz,dtp = "expired",0
    
    exp = {"expiry_date":exp_disp,"calendar_days_left":days_left,
           "est_trading_days":tdays,"theta_zone":tz,"est_daily_theta_pct":dtp,
           "strategy_bias":"sell premium" if 3<=days_left<=7 else ("buy options" if days_left>15 else ("balanced" if days_left>0 else "expired"))}
    
    # ── 12. MARKET REGIME (TUNED) ──
    print("[12/15] Market Regime")
    regime = classify_regime(vix_val, vix_history, adx_val, trend_dir, closes, atr_now, atr_20d)
    
    # ── 13. RISK ENGINE ──
    print("[13/15] Risk Engine")
    ann_vol = (vix_val or 15)/100
    day_vol = ann_vol/math.sqrt(252)
    per_vol = day_vol*math.sqrt(max(days_left,1))
    em1 = round((spot or 0)*per_vol, 1)
    em1p = round(per_vol*100, 2)
    var95 = round((spot or 0)*day_vol*1.645, 1)
    var99 = round((spot or 0)*day_vol*2.326, 1)
    
    mp_strike, mp_oi_max = None, 0
    if chain:
        for e in chain:
            s=e["strikePrice"]
            combo = (e.get("CE",{}).get("openInterest",0)or 0)+(e.get("PE",{}).get("openInterest",0)or 0)
            if combo>mp_oi_max: mp_oi_max=combo; mp_strike=s
    
    risk = {"spot":spot,"annualized_vol_pct":round(ann_vol*100,2),
            "daily_vol_pct":round(day_vol*100,3),
            "expected_move_1sd":em1,"expected_move_1sd_pct":em1p,
            "expected_move_2sd":round(em1*2,1) if em1 else None,
            "var_95_1day":var95,"var_99_1day":var99,
            "max_pain_estimate":{"strike":mp_strike,"combined_oi":mp_oi_max},
            "position_sizing":f"≤2% per trade, ≤6% portfolio | {em1p}% 1σ over {days_left}d" if spot else None}
    
    # ── 14. SCENARIO ANALYSIS (TUNED WEIGHTS) ──
    print("[14/15] Scenario Analysis")
    
    # Compute dynamic probabilities
    probs, adj = compute_scenario_weights(trend_dir, trend_str, vix_val, vix_pctl_6m, days_left, adx_val, rsi_v)
    
    bm = 1.15 if trend_dir=="bullish" else (0.85 if trend_dir=="bearish" else 1.0)
    bem = 0.85 if trend_dir=="bullish" else (1.15 if trend_dir=="bearish" else 1.0)
    
    bull_t = round((spot or 0)+em1*bm,1); bear_t = round((spot or 0)-em1*bem,1)
    base_u = round((spot or 0)+em1*0.3,1); base_d = round((spot or 0)-em1*0.3,1)
    
    scenario = {
        "spot": spot, "trend_bias": trend_dir,
        "probability_weights": {
            "method": "multi-factor dynamic weighting",
            "base_weights": {"bull": 34, "base": 38, "bear": 34, "tail": 5},
            "adjusted_weights_pct": probs,
            "adjustment_factors": adj,
        },
        "scenarios": {
            "bull_case": {"target":bull_t,"move_pct":round(em1p*bm,2),"probability_pct":probs["bull"],
                          "strategy":"Buy ATM/OTM calls, bull call spreads, sell OTM puts",
                          "key_resistances":[r["strike"] for r in oi_res[:2]]},
            "base_case": {"target_range":[base_d,base_u],"move_pct_range":[-round(em1p*0.3,2),round(em1p*0.3,2)],
                          "probability_pct":probs["base"],
                          "strategy":"Iron condor, short strangle, calendar spread"},
            "bear_case": {"target":bear_t,"move_pct":-round(em1p*bem,2),"probability_pct":probs["bear"],
                          "strategy":"Buy ATM/OTM puts, bear put spreads, sell OTM calls",
                          "key_supports":[s["strike"] for s in oi_sup[:2]]},
            "tail_risk": {"target_range":[round((spot or 0)-em1*2,1),round((spot or 0)+em1*2,1)],
                          "probability_pct":probs["tail"],
                          "strategy":"Long straddle/strangle, long VIX, tail hedges"},
        },
        "assumptions":{"vix":vix_val,"trend":trend_dir,"expected_1sd":em1,"days_to_expiry":days_left},
    }
    
    # ── 15. EXECUTIVE SUMMARY ──
    print("[15/15] Executive Summary")
    summary = {
        "symbol":"NIFTY 50","spot":spot,"change_pct":pct,"expiry":exp_disp,"days_to_expiry":days_left,
        "trend":f"{trend_dir} ({trend_str})","adx":adx_val,"rsi_14":rsi_v,
        "macd_signal":macd_cross,
        "india_vix":vix_val,"vix_regime":vr,"vix_percentile_6m":vix_pctl_6m,
        "pcr_oi":pcr_oi,"pcr_volume":pcr_vol,"atm_iv":round(atm_iv,1) if atm_iv else None,
        "max_pain_strike":mp_strike,
        "expected_1sd_move":f"±{em1p}% (±{em1} pts)" if em1 else None,
        "market_regime":regime["label"],
        "regime_confidence":regime["confidence"],
        "transition":regime["transition_state"],
        "scenario_probabilities":probs,
        "preferred_strategy":regime["strategy"],
        "option_bias":regime["option_bias"],
        "theta_zone":tz,
    }
    
    output = {
        "meta": {"symbol":"NIFTY 50","expiry":exp_disp,"lot_size":LOT_SIZE,
                 "timestamp":datetime.now().isoformat(),"data_source":"Yahoo Finance + CSV import",
                 "disclaimer":"Educational/research only. Not financial advice."},
        "1_market_data":mkt,
        "2_trend_analysis":trend,
        "3_option_chain":chain_s,
        "4_oi_analysis":oi,
        "5_iv_analysis":iv,
        "6_pcr":pcr_out,
        "7_volume_profile":vol,
        "8_rsi_macd":tech,
        "9_support_resistance":sr,
        "10_vix":vix_out,
        "11_expiry_theta":exp,
        "12_market_regime":regime,
        "13_risk_engine":risk,
        "14_scenario_analysis":scenario,
        "15_executive_summary":summary,
    }
    
    return output


# ─────────────── MAIN ───────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Nifty 50 Options Analysis Pipeline v2")
    parser.add_argument("--chain-csv", default=None, help="Path to option chain CSV file")
    parser.add_argument("--expiry", default=EXPIRY_DATE_STR, help="Expiry date YYYY-MM-DD")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()
    
    expiry_str = args.expiry
    expiry_display = EXPIRY_DISPLAY
    if expiry_str != EXPIRY_DATE_STR:
        try:
            dt = datetime.strptime(expiry_str, "%Y-%m-%d")
            expiry_display = dt.strftime("%d-%b-%Y")
        except:
            pass
    
    chain_csv_path = args.chain_csv
    
    print("="*60)
    print("  NIFTY 50 OPTIONS ANALYSIS v2 — TUNED REGIME ENGINE")
    print(f"  Expiry: {expiry_display} | Lot: {LOT_SIZE}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    if chain_csv_path:
        print(f"  Chain CSV: {chain_csv_path}")
    print("="*60); print()
    
    # Fetch data
    raw = fetch_yahoo_data()
    if not raw["nifty"]["spot"]:
        print("ERROR: Could not fetch Nifty spot", file=sys.stderr)
        sys.exit(1)
    
    # Load CSV option chain
    chain = load_option_chain_csv(chain_csv_path) if chain_csv_path else []
    
    # Run pipeline
    output = run_pipeline(raw, chain, expiry_str, expiry_display)
    
    # Print
    print("\n"+"="*60)
    print(json.dumps(output, indent=2, default=str))
    
    # Save
    out_path = args.output or os.path.join(os.path.dirname(os.path.abspath(__file__)) or ".",
                                           f"nifty_analysis_v2_{datetime.now().strftime('%Y-%m-%d')}.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n✅ Saved: {out_path}")
    
    return output


if __name__ == "__main__":
    main()
