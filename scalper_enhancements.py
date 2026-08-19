#!/usr/bin/env python3
"""
Scalper enhancements — CANDIDATE confirmation filters, OFF by default.

Frozen-strategy discipline: none of these are enabled unless the ablation
harness (option_backtest.ablate) measures a NET out-of-sample improvement over
baseline. Each is a pure, configurable, unit-tested predicate — no side effects,
no signal generation, no trade execution.

The five candidates:
  1. VWAP slope           — price side + VWAP slope direction must agree
  2. EMA separation / ATR — |EMA9 - EMA21|/ATR must beat a noise floor
  3. ADX direction        — ADX above threshold AND rising (not level alone)
  4. ORB breakout+retest  — genuine breakout → retest → continuation (confirmation)
  5. Option microstructure — fresh quote + spread + volume + OI + premium gate

Convention: every filter returns
    True   → condition confirms the trade (allow)
    False  → condition contradicts (block / NO_TRADE)
    None   → insufficient history / undefined → skip the filter (do NOT block)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Default thresholds — configurable at call sites; to be optimized on TRAINING
# data only, then evaluated on unseen OOS data.
ENH_DEFAULTS = {
    "vwap_window": 5,        # bars for VWAP slope
    "ema_sep_min": 0.5,      # |EMA9-EMA21|/ATR noise floor
    "adx_level": 25,         # ADX trend threshold
    "adx_slope_window": 5,   # bars for ADX slope
    "orb_tol": 0.003,        # retest tolerance (fraction of level)
    "orb_lookback": 15,      # bars to look back for breakout
    "micro_max_spread": 0.015,  # max bid/ask spread as fraction of mid
    "micro_min_oi": 500,        # min open interest (lots)
    "micro_min_vol": 1000,      # min cumulative volume
}


# ── Indicator additions (ATR + ADX — not in the frozen precompute) ──
def _true_range(highs, lows, closes):
    pc = closes.shift(1)
    return pd.concat([highs - lows, (highs - pc).abs(), (lows - pc).abs()],
                     axis=1).max(axis=1)


def atr(highs, lows, closes, n=14):
    """Wilder ATR(n)."""
    return _true_range(highs, lows, closes).ewm(alpha=1.0 / n, adjust=False).mean()


def adx(highs, lows, closes, n=14):
    """Wilder ADX(n) in [0, 100]. NaN where direction is undefined."""
    up = highs.diff()
    down = -lows.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=highs.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=highs.index)
    tr = _true_range(highs, lows, closes).replace(0, np.nan)
    atr_s = tr.ewm(alpha=1.0 / n, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr_s
    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denom
    return dx.ewm(alpha=1.0 / n, adjust=False).mean()


def attach_indicators(P, vwap_window=5, adx_slope_window=5):
    """Attach atr, adx, adx_slope, vwap_slope to a precompute dict (additive).

    Does not modify existing columns — the frozen scalper stays byte-identical.
    """
    highs, lows, closes = P["highs"], P["lows"], P["closes"]
    P["atr"] = atr(highs, lows, closes)
    P["adx"] = adx(highs, lows, closes)
    P["adx_slope"] = P["adx"].diff(adx_slope_window)
    P["vwap_slope"] = P["vwap"].diff(vwap_window)
    return P


# ── 1. VWAP slope ──────────────────────────────────────────────────
def vwap_slope_ok(P, i, side, window=5):
    """LONG: price > VWAP and VWAP rising. SHORT: price < VWAP and VWAP falling."""
    vw = P.get("vwap")
    if vw is None or i < window:
        return None
    cur = float(vw.iloc[i])
    prev = float(vw.iloc[i - window])
    if pd.isna(cur) or pd.isna(prev):
        return None
    spot = float(P["closes"].iloc[i])
    slope = cur - prev
    if side == 1:
        return spot > cur and slope > 0
    return spot < cur and slope < 0


# ── 2. EMA separation / ATR ────────────────────────────────────────
def ema_sep_atr_ok(P, i, side, min_sep=0.5):
    """Separation = (EMA9 - EMA21)/ATR. |sep| < min_sep = noise → block."""
    e9 = float(P["ema9"].iloc[i])
    e21 = float(P["ema21"].iloc[i])
    a = P["atr"].iloc[i]
    if pd.isna(a) or a <= 0:
        return None
    sep = (e9 - e21) / a
    if side == 1:
        return sep >= min_sep
    return sep <= -min_sep


# ── 3. ADX direction ───────────────────────────────────────────────
def adx_dir_ok(P, i, side, level=25):
    """Trend-strength gate: ADX above threshold AND rising (slope > 0).

    ADX is direction-agnostic; the side is supplied for a uniform interface but
    does not change the check. Returns None while ADX/slope are undefined.
    """
    a = P["adx"].iloc[i]
    s = P["adx_slope"].iloc[i]
    if pd.isna(a) or pd.isna(s):
        return None
    return bool(a >= level and s > 0)


# ── 4. ORB breakout + retest ───────────────────────────────────────
def orb_retest_ok(P, i, side, tol=0.003, lookback=15):
    """Detect a genuine breakout → retest → continuation of the opening range.

    LONG: within `lookback`, a high broke above ORB-high; a low subsequently
          retested the level (held within tol); current close is above it.
    SHORT: the mirror image around ORB-low.
    Returns None if ORB levels are undefined.
    """
    oh = P["orb_high"].iloc[i]
    ol = P["orb_low"].iloc[i]
    if pd.isna(oh) or pd.isna(ol):
        return None
    start = max(0, i - lookback)
    highs = P["highs"].iloc[start:i + 1]
    lows = P["lows"].iloc[start:i + 1]
    close = float(P["closes"].iloc[i])
    if side == 1:
        level = float(oh)
        broke = float(highs.max()) > level
        retested = float(lows.min()) <= level * (1 + tol)
        cont = close > level
    else:
        level = float(ol)
        broke = float(lows.min()) < level
        retested = float(highs.max()) >= level * (1 - tol)
        cont = close < level
    return bool(broke and retested and cont)


# ── 5. Option microstructure gate ──────────────────────────────────
def microstructure_ok(row, side, max_spread=0.015, min_oi=500, min_vol=1000,
                      min_premium=None):
    """Option-side gate on the selected strike's quote.

    `row` is the chain row dict (ce_*/pe_* fields) from option_backtest.
    Fails (False → NO_TRADE) when: no fresh quote, spread too wide, OI too low,
    volume too low, or premium too cheap. Never raises on missing fields.
    """
    pre = "ce" if side == 1 else "pe"
    bid = row.get(f"{pre}_bid")
    ask = row.get(f"{pre}_ask")
    ltp = row.get(f"{pre}_ltp")
    oi = row.get(f"{pre}_oi")
    vol = row.get(f"{pre}_vol")
    if ltp is None or ask is None:
        return False  # no fresh quote
    try:
        ask, ltp = float(ask), float(ltp)
        bid = float(bid) if bid is not None else ltp
    except (TypeError, ValueError):
        return False
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return False
    if (ask - bid) / mid > max_spread:
        return False
    if oi is not None and float(oi) < min_oi:
        return False
    if vol is not None and float(vol) < min_vol:
        return False
    if min_premium is not None and ltp < min_premium:
        return False
    return True
