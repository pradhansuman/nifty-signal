#!/usr/bin/env python3
"""
Option P&L Backtest — replay the Option Recorder's real chain snapshots through
the scalper's signal logic and simulate actual CE/PE round trips.

This closes the loop the spot backtest (scalper_backtest.py) leaves open: instead
of a zero-cost spot-points proxy, it trades the REAL option contract with:
  - 1-minute execution resolution (5m signal fires → next 1m fill)
  - real bid/ask (buy at ask, sell at bid) + configurable slippage
  - full cost model (brokerage + STT + exchange + stamp + GST)
  - MFE/MAE per trade, time-stop, S/R proximity filter, RVOL filter
  - walk-forward / out-of-sample chronological split
  - NET ₹ expectancy after ALL costs

Data source (Option Recorder, Path A):
  .openclaw/tmp/option_history/{asset}/{YYYY-MM-DD}.jsonl

Run:
  .openclaw/tmp/venv/bin/python3 option_backtest.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cost_model import round_trip_cost, cost_pct  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(HERE, ".openclaw", "tmp", "option_history")

LOT = {"nifty": 65, "bnf": 15}

# ── Configurable execution parameters ───────────────────────────────
DEFAULTS = {
    "target_pct": 0.10,      # +10% premium target (matches live build_call)
    "stop_pct": 0.10,        # -10% premium stop
    "hold_min": 10,          # time-stop (minutes)
    "slippage_rs": 0.10,     # ₹/unit, applied BEYOND the bid/ask spread
    "score_min": 3,          # scalper score threshold
    "sr_buffer": 15.0,       # S/R proximity buffer (spot points)
    "rvol_min": 1.0,         # RVOL threshold (>= 1.0 = above-average activity)
    "rvol_window": 15,       # RVOL rolling window (minutes)
    "train_frac": 0.70,      # walk-forward chronological split
    "delta_lo": 0.40,        # option selection delta bounds
    "delta_hi": 0.80,
}


# ── Data loading ────────────────────────────────────────────────────
def _parse_ts(s):
    return pd.Timestamp(s).tz_localize("Asia/Kolkata") if pd.Timestamp(s).tzinfo is None else pd.Timestamp(s)


def load_chain(asset="nifty", expiry=None):
    """Load all recorded JSONL for `asset` into (chain_df, minutes, spot_1m).

    Returns:
      chain_df : DataFrame indexed by minute (columns: strike, ce_bid, ce_ask,
                 ce_ltp, ce_oi, ce_vol, ce_delta, pe_*, spot, expiry)
      minutes  : sorted list of minute timestamps
      spot_1m  : Series of spot per minute
    """
    files = sorted(glob.glob(os.path.join(DATA_ROOT, asset, "*.jsonl")))
    if not files:
        return None, [], pd.Series(dtype=float)
    rows = []
    for f in files:
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
    if not rows:
        return None, [], pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].map(_parse_ts)
    df["minute"] = df["ts"].dt.floor("min")
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")

    # Use the dominant expiry (avoids mixing contracts across a roll-over).
    if expiry is None:
        expiry = df["expiry"].value_counts().idxmax()
    df = df[df["expiry"] == expiry].copy()

    df = df.drop_duplicates(subset=["minute", "strike"]).sort_values(["minute", "strike"])
    minutes = sorted(df["minute"].unique().tolist())

    # 1-minute spot series (one value per minute — all strikes share it).
    spot_1m = df.groupby("minute")["spot"].first().astype(float)

    return df, minutes, spot_1m


def build_5m(spot_1m):
    """Resample 1m spot → 5m OHLC (Volume = 0, like the live index feed)."""
    s = spot_1m
    ohlc = s.resample("5min", label="right", closed="right").ohlc()
    ohlc.columns = ["Open", "High", "Low", "Close"]
    ohlc["Volume"] = 0.0
    return ohlc.dropna(subset=["Close"])


# ── Signal generation (reuses the exact scalper scoring) ────────────
def generate_signals(df5m, score_min=None):
    """Run scalper_backtest scoring on 5m bars → list of signal dicts."""
    score_min = score_min if score_min is not None else DEFAULTS["score_min"]
    from scalper_backtest import precompute, score_at, in_window
    P = precompute(df5m)
    n = len(df5m)
    sigs = []
    for i in range(45, n - 1):
        ts = df5m.index[i]
        if not in_window(ts):
            continue
        if int(P["sess_count"].iloc[i]) < 4:
            continue
        sc = score_at(P, i)
        spot = float(P["closes"].iloc[i])
        e200 = float(P["ema200"].iloc[i])
        if sc >= score_min and spot >= e200:
            sigs.append({"ts": ts, "side": 1, "score": sc, "spot": spot})
        elif sc <= -score_min and spot <= e200:
            sigs.append({"ts": ts, "side": -1, "score": sc, "spot": spot})
    return sigs


# ── Chain lookup helpers ────────────────────────────────────────────
def _chain_lookup(df):
    """minute → {strike: row-dict}"""
    out = {}
    for minute, grp in df.groupby("minute"):
        out[minute] = {r["strike"]: r.to_dict() for _, r in grp.iterrows()}
    return out


def _select_strike(lookup, minute, side, spot, delta_lo, delta_hi):
    """Pick the tradeable strike for a side at a given minute.

    Prefers the ATM strike; among delta-eligible strikes picks the one closest
    to spot. Returns (strike, quote) or (None, None)."""
    rows = lookup.get(minute)
    if not rows:
        return None, None
    key = "ce_delta" if side == 1 else "pe_delta"
    elig = []
    for strike, r in rows.items():
        d = r.get(key)
        if d is None:
            continue
        if delta_lo <= abs(float(d)) <= delta_hi:
            elig.append((strike, r))
    if not elig:
        # fall back to nearest strike to spot
        elig = sorted(rows.items(), key=lambda kv: abs(kv[0] - spot))[:1]
        return elig[0] if elig else (None, None)
    elig.sort(key=lambda kv: abs(kv[0] - spot))
    return elig[0][0], elig[0][1]


def _quote(row, side):
    if side == 1:
        return (row.get("ce_bid"), row.get("ce_ask"), row.get("ce_ltp"),
                row.get("ce_oi"), row.get("ce_vol"), row.get("ce_delta"))
    return (row.get("pe_bid"), row.get("pe_ask"), row.get("pe_ltp"),
            row.get("pe_oi"), row.get("pe_vol"), row.get("pe_delta"))


# ── Filters (pure, testable) ────────────────────────────────────────
def sr_levels(df5m, i):
    """Floor-pivot S/R from the session so far (no lookahead). Returns (R1, S1)."""
    h = float(df5m["High"].iloc[: i + 1].max())
    l = float(df5m["Low"].iloc[: i + 1].min())
    c = float(df5m["Close"].iloc[i])
    p = (h + l + c) / 3.0
    r1 = 2 * p - l
    s1 = 2 * p - h
    return r1, s1


def sr_blocked(side, spot, r1, s1, buffer):
    """True if the entry is too close to a resistance (LONG) / support (SHORT)."""
    if side == 1:
        return spot <= r1 <= spot + buffer
    return spot - buffer <= s1 <= spot


def chain_activity(df, minute, window=15):
    """RVOL proxy = per-minute chain volume vs its rolling mean.

    Upstox volume is cumulative daily, so per-minute activity is the 1-minute
    diff of chain-wide (CE+PE) cumulative volume."""
    s = (df.groupby("minute")[["ce_vol", "pe_vol"]].sum().sum(axis=1))
    act = s.diff().fillna(0.0)
    mean = act.rolling(window, min_periods=3).mean()
    if minute not in mean.index or pd.isna(mean.loc[minute]) or mean.loc[minute] <= 0:
        return None
    return float(act.loc[minute] / mean.loc[minute])


# ── Trade execution ─────────────────────────────────────────────────
def run_option_trade(lookup, minutes, entry_idx, side, strike, params):
    """Simulate one CE/PE round trip starting at minutes[entry_idx].

    Buy at ask + slippage; target/stop on mid (ltp); exit at bid − slippage.
    Returns a trade dict with gross/net P&L, exit reason, MFE/MAE, duration."""
    tp = params["target_pct"]
    sp = params["stop_pct"]
    hold = params["hold_min"]
    slip = params["slippage_rs"]
    lot = params["lot"]

    bid, ask, ltp, oi, vol, delta = _quote(lookup.get(minutes[entry_idx], {}).get(strike), side)
    if not ask or not ltp:
        return None
    ask, ltp = float(ask), float(ltp)
    bid = float(bid) if bid else ltp

    entry_actual = ask + slip
    entry_mid = ltp
    target_mid = entry_mid * (1 + tp)
    stop_mid = entry_mid * (1 - sp)

    mfe = mae = 0.0
    exit_actual = None
    exit_reason = None
    exit_idx = entry_idx

    n = len(minutes)
    for j in range(entry_idx + 1, min(entry_idx + 1 + hold, n)):
        row = lookup.get(minutes[j], {}).get(strike)
        if not row:
            continue
        b, a, l, *_ = _quote(row, side)
        if l is None:
            continue
        l = float(l)
        mfe = max(mfe, l - entry_mid)
        mae = max(mae, entry_mid - l)
        exit_idx = j
        if l >= target_mid:
            exit_actual = (float(b) if b else l) - slip
            exit_reason = "TARGET"
            break
        if l <= stop_mid:
            exit_actual = (float(b) if b else l) - slip
            exit_reason = "STOP"
            break
    if exit_actual is None:
        # time-stop at the last managed minute
        b, a, l, *_ = _quote(lookup.get(minutes[exit_idx], {}).get(strike), side)
        exit_actual = (float(b) if b else float(entry_mid)) - slip
        exit_reason = "TIME"

    gross = (exit_actual - entry_actual) * lot
    cost = round_trip_cost(entry_actual, exit_actual, lot)
    net = gross - cost
    return {
        "side": side, "strike": strike, "entry": round(entry_actual, 2),
        "exit": round(exit_actual, 2), "reason": exit_reason,
        "gross": round(gross, 2), "cost": round(cost, 2), "net": round(net, 2),
        "mfe": round(mfe, 3), "mae": round(mae, 3),
        "duration_min": exit_idx - entry_idx,
        "oi": oi, "vol": vol, "delta": delta,
    }


def backtest(asset="nifty", expiry=None, filters=None, params=None):
    """Full pipeline: load → signals → option execution → trades list.

    filters: dict of optional gates {"sr": bool, "rvol": bool}.
    Returns (trades, meta) where meta carries diagnostics."""
    p = dict(DEFAULTS)
    if params:
        p.update(params)
    p.setdefault("lot", LOT.get(asset, 65))
    filters = filters or {}

    df, minutes, spot_1m = load_chain(asset, expiry)
    if df is None or len(minutes) < 20:
        return [], {"error": f"no recorded option data for {asset}"}
    df5m = build_5m(spot_1m)
    sigs = generate_signals(df5m, p["score_min"])
    lookup = _chain_lookup(df)

    # time index of each 5m signal for chronological walk-forward split
    t0 = minutes[0]
    t1 = minutes[-1]
    cut = t0 + (t1 - t0) * p["train_frac"]

    trades = []
    for sig in sigs:
        sts = sig["ts"]
        # next 1-minute snapshot strictly after the 5m signal close
        entry_idx = next((k for k, m in enumerate(minutes) if m > sts), None)
        if entry_idx is None:
            continue
        spot_at_entry = float(spot_1m.loc[minutes[entry_idx]]) if minutes[entry_idx] in spot_1m.index else sig["spot"]

        # S/R proximity filter
        if filters.get("sr"):
            # locate the 5m bar index for this signal (bar itself — no lookahead)
            pos = df5m.index.searchsorted(sts)
            if pos > 0:
                r1, s1 = sr_levels(df5m, int(pos))
                if sr_blocked(sig["side"], spot_at_entry, r1, s1, p["sr_buffer"]):
                    continue

        # RVOL filter (chain activity at the entry minute)
        if filters.get("rvol"):
            rv = chain_activity(df, minutes[entry_idx], p["rvol_window"])
            if rv is None or rv < p["rvol_min"]:
                continue

        strike, _ = _select_strike(lookup, minutes[entry_idx], sig["side"],
                                   spot_at_entry, p["delta_lo"], p["delta_hi"])
        if strike is None:
            continue
        t = run_option_trade(lookup, minutes, entry_idx, sig["side"], strike, p)
        if t is None:
            continue
        t["signal_ts"] = str(sts)
        t["entry_ts"] = str(minutes[entry_idx])
        t["split"] = "train" if minutes[entry_idx] < cut else "test"
        t["score"] = sig["score"]
        trades.append(t)

    meta = {
        "asset": asset, "expiry": expiry or df["expiry"].iloc[0],
        "snapshots": len(minutes), "signals": len(sigs),
        "bars_5m": len(df5m), "trades": len(trades),
        "cut": str(cut),
    }
    return trades, meta


# ── Reporting ───────────────────────────────────────────────────────
def _expectancy(trades):
    if not trades:
        return {"n": 0, "wr": None, "net": 0.0, "ev": None, "pf": None,
                "gw": 0.0, "gl": 0.0, "mfe": None, "mae": None, "r": None}
    nets = [t["net"] for t in trades]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n <= 0]
    wr = len(wins) / len(trades)
    gw = float(np.mean(wins)) if wins else 0.0
    gl = -float(np.mean(losses)) if losses else 0.0  # magnitude (positive)
    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")
    mfes = [t["mfe"] for t in trades if t["mfe"] is not None]
    maes = [t["mae"] for t in trades if t["mae"] is not None]
    mfe = float(np.mean(mfes)) if mfes else None
    mae = float(np.mean(maes)) if maes else None
    return {
        "n": len(trades), "wr": wr, "net": round(sum(nets), 2),
        "ev": round(float(np.mean(nets)), 2), "pf": round(pf, 2) if pf != float("inf") else None,
        "gw": round(gw, 2), "gl": round(gl, 2),
        "mfe": round(mfe, 3) if mfe is not None else None,
        "mae": round(mae, 3) if mae is not None else None,
        "r": round(mfe / mae, 2) if (mfe and mae) else None,
    }


def _print(label, trades):
    e = _expectancy(trades)
    print(f"  {label:<46} n={e['n']:<3} WR={e['wr'] if e['wr'] is not None else '-':>6} "
          f"EV=₹{e['ev'] if e['ev'] is not None else 0:>7} net=₹{e['net']:>8} PF={e['pf'] if e['pf'] is not None else '-':>5}")
    return e


def _split(trades, key):
    return [t for t in trades if t["split"] == key]


def main():
    asset = sys.argv[1] if len(sys.argv) > 1 else "nifty"
    df, minutes, spot_1m = load_chain(asset)
    if df is None:
        print(f"FAIL: no recorded option data for {asset}")
        return

    print(f"Option P&L Backtest — {asset.upper()} (recorded chain data)")
    print(f"  expiry {df['expiry'].iloc[0]} · {len(minutes)} 1m snapshots · "
          f"{len(df5m := build_5m(spot_1m))} 5m bars")
    print("=" * 100)

    # ── 1. BASE (no filters) + walk-forward ──
    trades, meta = backtest(asset, filters={})
    print(f"\nBASE  (target=stop=±{DEFAULTS['target_pct']:.0%}, hold {DEFAULTS['hold_min']}m, "
          f"slip ₹{DEFAULTS['slippage_rs']}/unit, {meta['signals']} signals)")
    if not trades:
        print("  no trades — not enough data yet (recorder needs more days)")
    else:
        _print("ALL", trades)
        _print("TRAIN (in-sample)", _split(trades, "train"))
        _print("TEST  (out-of-sample)", _split(trades, "test"))
        print(f"  exit mix: {dict(Counter(t['reason'] for t in trades))}")
        e = _expectancy(trades)
        if e["mfe"] is not None:
            print(f"  MFE avg ₹{e['mfe']} · MAE avg ₹{e['mae']} · R {e['r']} "
                  f"(favorable/adverse excursion)")

    # ── 2. S/R proximity filter (OOS comparison) ──
    t_sr, _ = backtest(asset, filters={"sr": True})
    print(f"\n+S/R proximity filter  (buffer ±{DEFAULTS['sr_buffer']} pts)")
    _print("ALL", t_sr)
    _print("TEST (OOS)", _split(t_sr, "test"))

    # ── 3. RVOL filter (OOS comparison) ──
    t_rv, _ = backtest(asset, filters={"rvol": True})
    print(f"\n+RVOL filter  (chain activity ≥ {DEFAULTS['rvol_min']}×, {DEFAULTS['rvol_window']}m window)")
    _print("ALL", t_rv)
    _print("TEST (OOS)", _split(t_rv, "test"))

    # ── 4. Both filters ──
    t_both, _ = backtest(asset, filters={"sr": True, "rvol": True})
    print("\n+S/R + RVOL")
    _print("ALL", t_both)
    _print("TEST (OOS)", _split(t_both, "test"))

    # ── 5. Time-stop sensitivity ──
    print("\nTime-stop sensitivity (BASE, no filters):")
    for hm in (5, 10, 15, 20, 30):
        t_hm, _ = backtest(asset, params={"hold_min": hm})
        _print(f"hold {hm:>2}m", t_hm)

    print("=" * 100)
    print("NOTE: NET expectancy is after bid/ask spread + slippage + full cost model")
    print("      (brokerage ₹20×2 + STT 0.1% + exchange + stamp + GST).")
    print("      Statistical significance needs ~2+ weeks of recorded data.")


if __name__ == "__main__":
    main()
