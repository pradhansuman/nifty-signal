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
import time
from datetime import datetime
from datetime import time as dtime

import numpy as np
import pandas as pd
import pytz
import yfinance as yf

sys.path.insert(0, ".")
import chain_table  # noqa: E402  (Upstox option chain for live premiums)
import delta_exchange  # noqa: E402  (Delta Exchange BTC options chain)
from market_session import india_market_session  # noqa: E402

# ── Multi-asset config ──
ASSETS = {
    "nifty":  {"symbol": "^NSEI",    "lot": 65, "options": True,  "vix": True,  "spot_tp": None,   "label": "NIFTY",
               # Real-time 1m (Upstox LTP feed) — the scalper needs fast bars
               "interval": "1m", "period": "5d",
               "trend_min": 1.0, "adx_min": 30, "hold_min": 30},
    "bnf":    {"symbol": "^NSEBANK", "lot": 15, "options": True,  "vix": True,  "spot_tp": None,   "label": "BANK NIFTY",
               # Backtest 2026-08-14 (15m): trend 0.5% + ADX 30 + 30m hold → PF 2.21, 56% WR
               "interval": "15m", "period": "60d",
               "trend_min": 0.5, "adx_min": 30, "hold_min": 30},
    "sensex": {"symbol": "^BSESN",   "lot": 20, "options": False, "vix": True,  "spot_tp": 0.0015, "label": "SENSEX",
               # Real-time 1m (Upstox LTP feed)
               "interval": "1m", "period": "5d",
               "trend_min": 1.0, "adx_min": 30, "hold_min": 30},
    "btc":    {"symbol": "BTC-USD",  "lot": 0,  "options": True,  "vix": False, "spot_tp": 0.005,  "label": "BITCOIN",
               # BTC runs on the 1h timeframe (5m is chop: PF ceiling 1.08).
               # Backtest 2026-08-14 (90d 1h): trend 1.5% + ADX 25 + 6h hold →
               # 182 trades, 56% WR, PF 1.30, +7,193 pts — the real BTC edge.
               "interval": "1h", "period": "60d", "hold_min": 360,
               "trend_min": 1.5, "adx_min": 25},
}
IST = pytz.timezone("Asia/Kolkata")


def _now():
    return datetime.now(IST).strftime("%H:%M:%S")


_vix_cache = {"ts": 0, "value": None}


def _load_tuning():
    """Runtime tuning overrides (no restart needed). Keys: score_min, trend_min,
    adx_min, vix_min, vix_max, theta_max. Read from .openclaw/tmp/scalper_tuning.json
    on every call; defaults come from env, then built-in defaults.

    Strict-after boundary: past SCALP_STRICT_AFTER (IST, default "15:35") the
    tuning file/env overrides are IGNORED and strict defaults are returned — so
    the 15:35 strict restore works on EVERY instance (Mac + Render), not just the
    one running the cron delete."""
    t = {}
    try:
        import os as _os
        p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".openclaw", "tmp", "scalper_tuning.json")
        if _os.path.exists(p):
            with open(p) as _f:
                t = json.load(_f)
    except Exception:
        t = {}
    defaults = {
        "score_min": float(os.environ.get("SCALP_SCORE_MIN", "3")),
        "trend_min": float(os.environ.get("SCALP_TREND_MIN", "0.8")),
        "adx_min": float(os.environ.get("SCALP_ADX_MIN", "25")),
        "vix_min": float(os.environ.get("SCALP_VIX_MIN", "12")),
        "vix_max": float(os.environ.get("SCALP_VIX_MAX", "18")),
        "theta_max": float(os.environ.get("SCALP_THETA_MAX", "0.5")),  # % of premium per 10-min hold
        "oi_min": float(os.environ.get("SCALP_OI_MIN", "500")),  # min option OI (lots) for a tradeable strike
        "funding_gate": float(os.environ.get("SCALP_FUNDING_GATE", "0.0005")),  # BTC: block the crowded carry side (0.05%/8h)
        "slope_atr_min": float(os.environ.get("SCALP_SLOPE_ATR_MIN", "1.0")),  # trend gate: min 200E drift (ATR units) for "trending"
        "window_open": False,  # override: ignore lunch-chop window block
        "regime_off": False,    # override: allow counter-trend scalps (chatty mode)
    }
    # Strict boundary (IST): after this time, force strict defaults everywhere.
    try:
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _zi
        strict_after = os.environ.get("SCALP_STRICT_AFTER", "15:35")
        now_ist = _dt.now(_zi("Asia/Kolkata")).strftime("%H:%M")
        if now_ist >= strict_after:
            return defaults
    except Exception:
        pass
    for k, v in t.items():
        if k not in defaults:
            continue
        if k in ("window_open", "regime_off"):
            defaults[k] = bool(v)
        else:
            defaults[k] = float(v)
    return defaults


def _vix_level():
    """Current Nifty VIX close (cached 30 min; fail-open returns None)."""
    import time as _t
    if _t.time() - _vix_cache["ts"] < 1800:
        return _vix_cache["value"]
    try:
        import yfinance as yf
        v = yf.download("^INDIAVIX", period="5d", interval="1d", progress=False, auto_adjust=True)
        if isinstance(v.columns, pd.MultiIndex):
            v.columns = v.columns.get_level_values(0)
        val = float(v["Close"].iloc[-1])
        _vix_cache.update({"ts": _t.time(), "value": val})
        return val
    except Exception:
        return _vix_cache["value"] or None


def _adx(df, n=14):
    """Wilder ADX on 5m bars (index-preserving)."""
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    c = df["Close"].astype(float)
    up = h.diff()
    dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h - l, np.maximum((h - c.shift()).abs(), (l - c.shift()).abs()))
    atr = pd.Series(tr, index=df.index).ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def _infer_interval_minutes(df):
    """Infer the bar timeframe (minutes) from median spacing of the index."""
    if df is None or len(df) < 2:
        return None
    deltas = df.index.to_series().diff().dropna().dt.total_seconds().abs() / 60.0
    if len(deltas) == 0:
        return None
    med = float(deltas.median())
    for cand in (1, 5, 15, 30, 60):
        if abs(med - cand) <= cand * 0.30:
            return cand
    return max(1, int(round(med)))


def _orb_window(sess_df):
    """15-minute opening range, anchored to 09:15-09:30 IST (NOT "first N bars").

    Returns dict(orb_high, orb_low, available, note).
    - Infers the feed timeframe from bar spacing (robust to config drift).
    - A feed coarser than 15m cannot represent a 15-min ORB → available=False
      (never silently substitute a 60-min range for a 15-min one).
    - Selects only bars whose IST wall-clock falls in [09:15, 09:30); pre-market,
      missing, or not-yet-formed bars are excluded.
    """
    if sess_df is None or len(sess_df) < 2:
        return {"orb_high": None, "orb_low": None, "available": False, "note": "no session data"}
    tf = _infer_interval_minutes(sess_df)
    if tf is None:
        return {"orb_high": None, "orb_low": None, "available": False, "note": "cannot infer timeframe"}
    if tf > 15:
        return {"orb_high": None, "orb_low": None, "available": False,
                "note": "feed {}m is coarser than 15m — no 15-min ORB".format(tf)}
    t = sess_df.index.time
    mask = (t >= dtime(9, 15)) & (t < dtime(9, 30))
    orb = sess_df[mask]
    if len(orb) == 0:
        return {"orb_high": None, "orb_low": None, "available": False,
                "note": "opening 15 min not formed (pre-09:15 or missing bars)"}
    return {"orb_high": float(orb["High"].max()), "orb_low": float(orb["Low"].min()),
            "available": True, "note": "09:15-09:30 IST ({} {}m bars)".format(len(orb), tf)}


def _trend_strength_block(bias, slope_atr, slope_atr_min=1.0):
    """Direction-aware, normalized trend-strength gate (returns reason or None).

    STRENGTH is the 200 EMA's drift over the slope window, measured in ATR units
    (slope_atr = (EMA200_now − EMA200_prev) / ATR14). This is what actually
    separates a trending day (200E drifting several ATRs) from chop (200E drifting
    ~0 ATR) — raw % distance does NOT: a 0.09% distance can be a decisive move
    when ATR is tiny, and a flat 200E is chop regardless of how far price is.
    DIRECTION is enforced separately by the regime filter (which side of the 200E).
    """
    if bias == "LONG" and slope_atr < slope_atr_min:
        return "200 EMA drifting {:.2f} ATR < {:.2f} ATR — no rising trend".format(slope_atr, slope_atr_min)
    if bias == "SHORT" and slope_atr > -slope_atr_min:
        return "200 EMA drifting {:.2f} ATR > -{:.2f} ATR — no falling trend".format(slope_atr, slope_atr_min)
    return None


def _orb_position(spot, orb_high, orb_low):
    """Classify spot vs the 15-min opening range: ABOVE / INSIDE / BELOW / N/A."""
    if orb_high is None or orb_low is None:
        return "N/A"
    if spot > orb_high:
        return "ABOVE"
    if spot < orb_low:
        return "BELOW"
    return "INSIDE"


def get_bars(asset="nifty", period="5d", interval="5m"):
    # Real-time Upstox candles for Indian indices (1m feed, resampled) — the
    # primary source. Yahoo is only a fallback when Upstox is unreachable.
    if asset in ("nifty", "bnf", "sensex"):
        try:
            import upstox_rt as _urt
            rule = {"1m": "1min", "5m": "5min", "15m": "15min",
                    "30m": "30min", "1h": "1h"}.get(interval, "1min")
            df = _urt.get_bars(asset, rule=rule)
            if df is not None and len(df) >= 20:
                return df
        except Exception:
            pass
    df = yf.download(ASSETS[asset]["symbol"], period=period, interval=interval, progress=False, auto_adjust=True)
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


def _spot_call(asset, spot, bias):
    """Spot-level call (used for sensex, and as BTC fallback when the options
    chain is unavailable). Entry/target/stop directly on the price. For BTC the
    tradable quote is the Delta BTCUSDT perpetual futures mark (funding
    attached) → the call is labelled BTC PERP."""
    cfg = ASSETS[asset]
    tp = cfg["spot_tp"]
    if bias == "LONG":
        target, stop = spot * (1 + tp), spot * (1 - tp)
    else:
        target, stop = spot * (1 - tp), spot * (1 + tp)
    call = {
        "option": "{} {}".format("LONG" if bias == "LONG" else "SHORT", cfg["label"]),
        "strike": round(spot, 2), "premium": round(spot, 2),
        "expiry": "INTRAday",
        "entry": round(spot, 2), "buy_ask": round(spot, 2),
        "target": round(target, 2), "stop": round(stop, 2),
        "lot_cost": 0, "spread": 0.0, "spread_pct": 0.0, "half_spread": 0.0,
        "delta": None, "theta": None, "oi": None, "volume": None,
        "target_pts": round(spot * tp, 0), "stop_pts": round(spot * tp, 0),
    }
    if asset == "btc":
        call["futures"] = True
        call["option"] = "{} BTC PERP".format("LONG" if bias == "LONG" else "SHORT")
        try:
            fut = delta_exchange.get_btc_futures()
            call["funding"] = fut.get("funding")
            call["feed"] = fut.get("source") if fut.get("price") else "yf-spot"
        except Exception:
            call["feed"] = "yf-spot"
    return call


def build_call(asset, spot, bias, expiry):
    """Build the actionable call for an asset.
    Options assets (nifty/bnf/btc): spread-aware strike selection from the
    chain (delta 0.40-0.80, tightest spread, >3% blocks, theta guard,
    target/stop net of spread). BTC chain comes from Delta Exchange.
    Spot assets (sensex): entry/target/stop directly on the price.
    BTC falls back to a spot call if the options chain is unavailable."""
    cfg = ASSETS[asset]
    if not cfg["options"]:
        return _spot_call(asset, spot, bias)
    try:
        if asset == "btc":
            ch = delta_exchange.get_btc_chain()
        else:
            ch = chain_table.get_chain(asset="banknifty" if asset == "bnf" else "nifty")
        rows = ch.get("rows") or []
        if not rows:
            return _spot_call(asset, spot, bias) if asset == "btc" else None
        cands = []
        for r in rows:
            strike = r.get("strike") or 0
            if bias == "LONG":
                ltp, bid, ask, delta = r.get("ce_ltp"), r.get("ce_bid"), r.get("ce_ask"), r.get("ce_delta")
                theta = r.get("ce_theta")
                oi = r.get("ce_oi")
                vol = r.get("ce_vol")
            else:
                ltp, bid, ask, delta = r.get("pe_ltp"), r.get("pe_bid"), r.get("pe_ask"), r.get("pe_delta")
                theta = r.get("pe_theta")
                oi = r.get("pe_oi")
                vol = r.get("pe_vol")
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
                "theta": float(theta) if theta is not None else None,
                "oi": float(oi) if oi else 0,
                "volume": float(vol) if vol else 0,
            })
        if not cands:
            return None
        # ── Liquidity: prefer strikes with real OI (volume confirms participation).
        #    Skip dead strikes; if the whole chain is thin, fall back to spread-only
        #    selection (the spread filter below still applies). ──
        _oi_min = _load_tuning().get("oi_min", 500)
        _liquid = [c for c in cands if c["oi"] >= _oi_min]
        if _liquid:
            cands = _liquid
        cands.sort(key=lambda c: c["spread_pct"])
        best = cands[0]
        if best["spread_pct"] > 3.0:
            return {"blocked": True, "block_reason":
                    "spread {:.1f}% of premium — target +10% can't beat it".format(best["spread_pct"])}
        # ── Theta guard: block only pathological decay. Metric = % of premium
        #    lost in a 10-min hold (the scalp horizon): abs(theta)/premium * 10/1440.
        #    Default 0.5 (%/10min) — normal options are 0.05-0.4%; only near-expiry
        #    monsters exceed it. (Per-day % was misleading: deep-ITM options have
        #    high theta/premium but negligible 10-min decay.)
        tun_bc = _load_tuning()
        theta_max = tun_bc["theta_max"]
        theta_10 = abs(best["theta"]) / best["ltp"] * (10.0 / 1440.0) * 100.0 if best["theta"] else 0.0
        if best["theta"] is not None and theta_10 > theta_max:
            return {"blocked": True, "block_reason":
                    "theta {:.2f} = {:.2f}%/10min of premium — pathological decay".format(
                        best["theta"], theta_10)}
        prem = best["ltp"]
        # ── Spread-aware target/stop: you BUY at ask, SELL at bid. To net ±10%
        #    (exit at bid), the tracked mid premium must move ±10% PLUS half the
        #    spread. Target/stop below are in tracked-mid terms. ──
        half_spread = best["spread"] / 2
        target = prem * 1.10 + half_spread
        stop = prem * 0.90 - half_spread
        return {
            "option": "Buy {:,} {}".format(best["strike"], "CE" if bias == "LONG" else "PE"),
            "strike": best["strike"],
            "premium": round(prem, 2),
            "expiry": ch.get("expiry") or expiry,
            "entry": round(prem, 2),
            "buy_ask": round(float(ask), 2) if ask else round(prem, 2),
            "target": round(target, 2),
            "stop": round(stop, 2),
            "lot_cost": round(prem * ASSETS[asset]["lot"], 0),
            "spread": round(best["spread"], 2),
            "spread_pct": round(best["spread_pct"], 2),
            "half_spread": round(half_spread, 2),
            "delta": best["delta"],
            "theta": best["theta"],
            "oi": best["oi"],
            "volume": best["volume"],
            "target_pts": round(spot * 0.0015, 0),
            "stop_pts": round(spot * 0.0009, 0),
        }
    except Exception:
        if asset == "btc":
            return _spot_call(asset, spot, bias)  # Delta chain failed → spot fallback
        return None
    return None


def optionize(asset, direction, spot_entry, spot_stop, spot_target):
    """Map a spot-level entry/stop/target (index points) onto the ATM option's
    premium terms using its delta — turns spot cross/reclaim alerts into a
    tradeable option call (strike + premium entry/stop/target + lot cost)."""
    if asset not in ("nifty", "bnf") or not spot_entry:
        return None
    try:
        ch = chain_table.get_chain(asset=asset)
        rows = ch.get("rows") or []
        spot = spot_entry or ch.get("chain_spot")
        if not rows or not spot:
            return None
        atm = ch.get("atm") or min(rows, key=lambda r: abs((r.get("strike") or 0) - spot))["strike"]
        row = next((r for r in rows if r.get("strike") == atm), None)
        if not row:
            return None
        side = "CE" if direction == "LONG" else "PE"
        ltp = row.get("ce_ltp" if side == "CE" else "pe_ltp")
        delta = row.get("ce_delta" if side == "CE" else "pe_delta")
        ask = row.get("ce_ask" if side == "CE" else "pe_ask")
        if ltp is None:
            return None
        ltp = float(ltp)
        d = abs(float(delta)) if delta is not None else 0.5  # ATM ~0.5 fallback
        loss_spot = abs(spot_entry - spot_stop)
        gain_spot = abs(spot_target - spot_entry)
        stop_prem = ltp - loss_spot * d
        target_prem = ltp + gain_spot * d
        if stop_prem <= 0:
            stop_prem = round(ltp * 0.5, 2)
        lot = ASSETS[asset]["lot"]
        return {
            "option": "Buy {:,} {}".format(int(atm), side),
            "strike": int(atm),
            "side": side,
            "entry": round(ltp, 2),
            "stop": round(stop_prem, 2),
            "target": round(target_prem, 2),
            "delta": round(d, 2),
            "ask": round(float(ask), 2) if ask else round(ltp, 2),
            "lot_cost": round(ltp * lot, 0),
            "expiry": ch.get("expiry"),
        }
    except Exception:
        return None


def _funding_gate(asset, bias, funding, gate=0.0005):
    """BTC funding-rate gate: block the side that pays carry. Returns
    (bias, block_text). Fail-open (no block) for non-BTC or missing funding."""
    if asset != "btc" or funding is None or bias == "FLAT":
        return bias, None
    if bias == "LONG" and funding > gate:
        return "FLAT", "funding +{:.3f}% — longs pay carry, skip LONG".format(funding * 100)
    if bias == "SHORT" and funding < -gate:
        return "FLAT", "funding {:.3f}% — shorts pay carry, skip SHORT".format(funding * 100)
    return bias, None


def main(asset="nifty"):
    t0 = time.perf_counter()
    out = {"signal": "WAIT", "bias": "FLAT", "score": 0, "spot": None, "timestamp": _now(), "asset": asset}
    cfg = ASSETS[asset]
    if asset != "btc":
        session = india_market_session(datetime.now(IST))
        out["market_open"] = session["open"]
        if not session["open"]:
            out.update({
                "window": "BLOCKED",
                "window_reason": session["reason"],
                "blocking_gates": [{"gate": "Market session", "reason": session["reason"]}],
                "reason": session["reason"],
                "latency_ms": {"data": 0, "signal": 0, "decision": 0,
                               "total": round((time.perf_counter() - t0) * 1000, 1)},
            })
            return out
    else:
        out["market_open"] = True  # Bitcoin trades continuously.
    df = get_bars(asset, period=cfg.get("period", "5d"), interval=cfg.get("interval", "5m"))
    t1 = time.perf_counter()
    if df is None or len(df) < 40:
        out["reason"] = "Not enough bars yet (need 40)"
        out["latency_ms"] = {"data": round((t1 - t0) * 1000, 1), "signal": 0, "decision": 0, "total": round((t1 - t0) * 1000, 1)}
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
    # BTC tradable quote = Delta BTCUSDT perpetual futures mark (live), funding
    # attached. Falls back to the yfinance close if Delta is unreachable.
    if asset == "btc":
        try:
            fut = delta_exchange.get_btc_futures()
            if fut.get("price"):
                spot = float(fut["price"])
                out["feed"] = fut.get("source")
            else:
                out["feed"] = "yf-spot"
            out["funding"] = fut.get("funding")
        except Exception:
            out["feed"] = "yf-spot"
    out["spot"] = round(spot, 2)

    # Live LTP for the decision — the last bar close can lag the real quote by
    # up to a minute. VWAP/ORB/trend comparisons must use the SAME live price the
    # dashboard shows; bar-based indicators (EMA/RSI/Stoch/ADX) stay on closes.
    if asset in ("nifty", "bnf", "sensex"):
        try:
            import upstox_rt as _urt
            _live = _urt.last_price(asset)
            if _live:
                spot = float(_live)
        except Exception:
            pass
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
    # ATR(14) for momentum normalization — a raw "7-point" move means nothing
    # without volatility context; classify strength in ATR units instead.
    tr = pd.concat([(df["High"] - df["Low"]).clip(lower=0),
                    (df["High"] - df["Close"].shift(1)).abs(),
                    (df["Low"] - df["Close"].shift(1)).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else 0.0
    mom_atr = mom / atr if atr > 0 else 0.0
    # Opening Range = first 15 minutes (09:15-09:30 IST), not "first N bars".
    # Anchored to the exchange open; coarse feeds (>15m) → ORB unavailable.
    orb = _orb_window(sess)
    orb_high = orb["orb_high"]
    orb_low = orb["orb_low"]
    out["orb_available"] = orb["available"]
    out["orb_note"] = orb["note"]

    score = 0
    reasons = []
    breakdown = []  # [{gauge, points, note}] — auditable score trail

    def _add(gauge, pts, note):
        nonlocal score
        score += pts
        reasons.append("{} ({:+d})".format(note, pts))
        breakdown.append({"gauge": gauge, "points": pts, "note": note})

    _add("EMA 9/21", 2 if e9 > e21 else -2,
         "EMA9 {:.0f} {} EMA21 {:.0f}".format(e9, ">" if e9 > e21 else "<", e21))
    if cross_up:
        _add("EMA cross", 2, "fresh golden cross")
    if cross_down:
        _add("EMA cross", -2, "fresh death cross")
    _add("VWAP", 1 if spot > vwap_now else -1,
         "{} VWAP {:.0f}".format("above" if spot > vwap_now else "below", vwap_now))
    _add("Momentum", 1 if mom > 0 else -1, "momentum {}{:.1f}".format("+" if mom > 0 else "", mom))
    if r > 70:
        _add("RSI", -1, "RSI {:.0f} overbought".format(r))
    elif r < 30:
        _add("RSI", 1, "RSI {:.0f} oversold".format(r))
    else:
        _add("RSI", 0, "RSI {:.0f} neutral".format(r))
    if k > 80:
        _add("Stoch", -1, "Stoch {:.0f} overbought".format(k))
    elif k < 20:
        _add("Stoch", 1, "Stoch {:.0f} oversold".format(k))
    else:
        _add("Stoch", 0, "Stoch {:.0f} neutral".format(k))
    _orb_pos = _orb_position(spot, orb_high, orb_low)
    if _orb_pos == "ABOVE":
        _add("ORB", 1, "above ORB high {:.0f}".format(orb_high))
    elif _orb_pos == "BELOW":
        _add("ORB", -1, "below ORB low {:.0f}".format(orb_low))
    elif _orb_pos == "INSIDE":
        _add("ORB", 0, "inside ORB {:.0f}-{:.0f}".format(orb_low, orb_high))
    else:
        _add("ORB", 0, "ORB N/A ({})".format(orb["note"]))

    tun = _load_tuning()
    # Per-asset gate overrides (BTC is choppier → stricter gates than Nifty/BNF)
    score_min = float(cfg.get("score_min", tun["score_min"]))
    out["score_min"] = score_min
    bias = "LONG" if score >= score_min else "SHORT" if score <= -score_min else "FLAT"
    # Preserve the raw directional read separately from the gated execution
    # bias. A bullish score can be valid while tradeability is blocked.
    score_bias = bias

    # ── 200 EMA regime filter: DIRECTION — never scalp against the trend ──
    ema200_series = closes.ewm(span=200, adjust=False).mean()
    ema200 = float(ema200_series.iloc[-1])
    out["ema200"] = round(ema200, 2)
    # 200E slope over a ~2-hour horizon (duration-based, scales with timeframe)
    _slope_tf = _infer_interval_minutes(df) or 5
    _slope_bars = max(2, int(round(120.0 / _slope_tf)))
    ema200_prev = float(ema200_series.iloc[-_slope_bars - 1]) if len(ema200_series) >= _slope_bars + 1 else ema200
    ema200_slope = (ema200 - ema200_prev) / ema200_prev * 100.0 if ema200_prev else 0.0
    ema200_slope_atr = (ema200 - ema200_prev) / atr if atr > 0 else 0.0
    out["trend_dir"] = "ABOVE" if spot > ema200 else "BELOW"
    out["ema200_slope"] = round(ema200_slope, 3)
    out["ema200_slope_atr"] = round(ema200_slope_atr, 2)
    regime_block = None
    if score_bias == "LONG" and spot < ema200 and not tun.get("regime_off"):
        regime_block = "counter-trend LONG blocked (spot below 200 EMA {:.0f})".format(ema200)
        bias = "FLAT"
    elif score_bias == "SHORT" and spot > ema200 and not tun.get("regime_off"):
        regime_block = "counter-trend SHORT blocked (spot above 200 EMA {:.0f})".format(ema200)
        bias = "FLAT"

    # ── Trend-strength gate: STRENGTH = 200E drift (ATR-normalized) ──
    # (Redesign 2026-08-21: the old gate used raw |spot-200E| % as a "strength"
    # proxy — conceptually wrong: 0.09% distance can be a decisive move when ATR
    # is tiny, and a flat 200E is chop regardless of % distance. The 200E's own
    # drift (in ATR units) is what separates trend from chop.
    # NOTE: this gate is UNVALIDATED — the old PF 1.53 backtest was for the raw
    # % gate and does NOT transfer. Must go through the research/ablation loop.)
    slope_atr_min = float(tun.get("slope_atr_min", 1.0))
    trend_dist = abs(spot - ema200) / ema200 * 100.0
    trend_dist_atr = (spot - ema200) / atr if atr > 0 else 0.0
    out["trend_dist"] = round(trend_dist, 2)
    out["trend_dist_atr"] = round(trend_dist_atr, 2)
    out["slope_atr_min"] = slope_atr_min
    trend_block = None
    if score_bias != "FLAT":
        trend_block = _trend_strength_block(score_bias, ema200_slope_atr, slope_atr_min)
        if trend_block:
            bias = "FLAT"

    # ── ADX trend-strength gate (backtest 2026-08-14: ADX>25 → PF 1.82) ──
    adx_min = float(cfg.get("adx_min", tun["adx_min"]))
    adx_series = _adx(df)
    adx_val = float(adx_series.iloc[-1]) if not pd.isna(adx_series.iloc[-1]) else 0.0
    out["adx"] = round(adx_val, 1)
    out["adx_gate"] = adx_min
    adx_block = None
    if score_bias != "FLAT" and adx_val < adx_min:
        adx_block = "ADX {:.2f} < {:.1f} — no sustained trend".format(adx_val, adx_min)
        bias = "FLAT"

    # ── VIX regime gate (backtest: VIX 12-18 + ADX>25 → PF 1.96, WR 66%) ──
    vix_min = tun["vix_min"]
    vix_max = tun["vix_max"]
    vix_val = _vix_level() if ASSETS[asset]["vix"] else None
    out["vix"] = round(vix_val, 2) if vix_val else None
    out["vix_gate"] = [vix_min, vix_max]
    vix_block = None
    if score_bias != "FLAT" and vix_val is not None and not (vix_min <= vix_val <= vix_max):
        vix_block = "VIX {:.1f} outside {:.0f}-{:.0f} — premium too cheap/expensive for scalps".format(
            vix_val, vix_min, vix_max)
        bias = "FLAT"

    # ── BTC funding-rate gate: don't pay carry on the crowded side ──
    # Positive funding → longs pay shorts → SHORT earns, LONG costs. Skip the
    # paying side when funding is meaningfully one-sided (fail-open when None).
    funding_block = None
    _, funding_block = _funding_gate(asset, score_bias, out.get("funding"), tun.get("funding_gate", 0.0005))
    if funding_block:
        bias = "FLAT"

    # ── Time-of-day window: avoid lunch chop (BTC = 24/7) ──
    now_dt = datetime.now(IST)
    hm = now_dt.hour * 60 + now_dt.minute
    window_open = (9 * 60 + 20) <= hm <= (11 * 60 + 45) or (13 * 60 + 30) <= hm <= (15 * 60 + 20)
    if ASSETS[asset]["label"] == "BITCOIN":
        window_open = True  # crypto trades 24/7
    if tun.get("window_open"):
        window_open = True  # today-only override via tuning file
    out["window"] = "ACTIVE" if window_open else "BLOCKED"
    out["window_reason"] = (
        "Scalp window ACTIVE (9:20-11:45, 13:30-15:20)" if window_open
        else "Scalp window BLOCKED — lunch chop 11:45-13:30 / pre-9:20")
    window_block = None
    if not window_open and score_bias != "FLAT":
        window_block = out["window_reason"]
        bias = "FLAT"

    # ── PERFECT SETUP: every gate passes AND momentum/VWAP/RSI all align ──
    perfect = False
    if bias != "FLAT":
        mom_ok = mom >= 30 if bias == "LONG" else mom <= -30
        vwap_ok = spot >= vwap_now if bias == "LONG" else spot <= vwap_now
        rsi_ok = r >= 50 if bias == "LONG" else r <= 50
        perfect = (score >= score_min and trend_block is None
                   and adx_val >= adx_min and mom_ok and vwap_ok and rsi_ok)
    out["perfect"] = perfect

    prev_k = float(kk.iloc[-2]) if len(kk) >= 2 else k
    prev_d = float(dd.iloc[-2]) if len(dd) >= 2 else dline
    stoch_crossed = None
    if prev_k >= prev_d and k < dline:
        stoch_crossed = "bearish crossover"
    elif prev_k <= prev_d and k > dline:
        stoch_crossed = "bullish crossover"

    _blocks = []
    trend_reasons = [reason for reason in (regime_block, trend_block) if reason]
    if trend_reasons:
        _blocks.append({"gate": "Trend", "reason": "; ".join(trend_reasons)})
    if adx_block:
        _blocks.append({"gate": "ADX", "reason": adx_block})
    if vix_block:
        _blocks.append({"gate": "VIX", "reason": vix_block})
    if funding_block:
        _blocks.append({"gate": "Funding", "reason": funding_block})
    if window_block:
        _blocks.append({"gate": "Window", "reason": window_block})

    out.update({
        "bias": bias, "score": score, "score_met": abs(score) >= score_min,
        "score_bias": score_bias,
        "ema9": round(e9, 2), "ema21": round(e21, 2),
        "vwap": round(vwap_now, 2),
        "vwap_pct": round((spot - vwap_now) / vwap_now * 100.0, 3) if vwap_now else None,
        "rsi": round(r, 1),
        "stoch_k": round(k, 1), "stoch_d": round(dline, 1),
        "stoch_cross": "K<D weakening" if k < dline else ("K>D strengthening" if k > dline else "K=D"),
        "stoch_crossed": stoch_crossed,
        "momentum": round(mom, 2), "momentum_atr": round(mom_atr, 2),
        "orb_high": round(orb_high, 2) if orb_high is not None else None,
        "orb_low": round(orb_low, 2) if orb_low is not None else None,
        "blocking_gates": _blocks,
        "reasons": reasons,
        "score_breakdown": breakdown,
        "reason": "; ".join(reasons),
    })

    if bias == "FLAT":
        out["signal"] = "WAIT"
        block_txt = "; ".join(x for x in (regime_block, trend_block, adx_block, vix_block, funding_block, window_block) if x)
        if abs(score) >= score_min and block_txt:
            # score CLEARED the ±threshold but a gate blocked the trade
            out["reason"] = "score {:+d} (≥ ±{:.0f}) but {} — {}".format(
                score, score_min, block_txt, "; ".join(reasons))
        elif abs(score) < score_min:
            out["reason"] = "score {:+d} below ±{:.0f} threshold — {}".format(
                score, score_min, "; ".join(reasons))
        else:
            out["reason"] = "No scalp edge — score {:+d}. {}".format(score, "; ".join(reasons))
        t_flat = time.perf_counter()
        out["latency_ms"] = {
            "data": round((t1 - t0) * 1000, 1),
            "signal": round((t_flat - t1) * 1000, 1),
            "decision": 0,
            "total": round((t_flat - t0) * 1000, 1),
        }
        return out

    out["signal"] = "SCALP_LONG" if bias == "LONG" else "SCALP_SHORT"
    out["confidence"] = min(100, abs(score) * 14)
    t2 = time.perf_counter()
    call = build_call(asset, spot, bias, out.get("expiry"))
    t3 = time.perf_counter()
    out["latency_ms"] = {
        "data": round((t1 - t0) * 1000, 1),
        "signal": round((t2 - t1) * 1000, 1),
        "decision": round((t3 - t2) * 1000, 1),
        "total": round((t3 - t0) * 1000, 1),
    }
    # BTC options on Delta are often 5-7% spread → the honest filter blocks them.
    # Fall back to a spot-level BTC call rather than showing nothing.
    if asset == "btc" and (call is None or call.get("blocked")):
        call = _spot_call(asset, spot, bias)
    out["call"] = call
    if call is None:
        out["reason"] = "{} scalp (score {:+d}) but no option premium available from Upstox chain".format(bias, score)
    elif call.get("blocked"):
        out["reason"] = "{} scalp (score {:+d}) but NO TRADE — {}".format(bias, score, call.get("block_reason", ""))
    else:
        # 10-minute signal freshness window
        from datetime import timedelta
        call["expires_at"] = (now_dt + timedelta(minutes=cfg.get("hold_min", 10))).strftime("%H:%M")
        call["expires_dt"] = (now_dt + timedelta(minutes=cfg.get("hold_min", 10))).isoformat()
        out["reason"] = "{} scalp — score {:+d}. {}".format(bias, score, "; ".join(reasons))
    return out


if __name__ == "__main__":
    print(json.dumps(main(), default=str))
