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
  data/option_history/{asset}/{YYYY-MM-DD}.jsonl

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
from option_recorder import BASE as DATA_ROOT  # noqa: E402

import scalper_enhancements as enh  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

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

    # Expiry selection — each trading day keeps ITS OWN dominant expiry (the
    # live weekly chain actually traded that day). A single GLOBAL dominant
    # expiry would silently discard every other week once the dataset spans
    # multiple expiries (chain rolls at expiry day-change).
    if expiry is not None:
        # Explicit expiry → single-contract study (global filter, unchanged).
        df = df[df["expiry"] == expiry].copy()
    else:
        day = df["ts"].dt.date
        parts = []
        for _d, grp in df.groupby(day, sort=True):
            dom = grp["expiry"].value_counts().idxmax()
            parts.append(grp[grp["expiry"] == dom])
        df = pd.concat(parts).copy() if parts else df.iloc[0:0]

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
        # No delta-eligible contract → skip the trade (respect the 0.40–0.80
        # contract-selection rule). Do NOT fall back to nearest strike.
        return None, None
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
    p.update(enh.ENH_DEFAULTS)          # configurable enhancement thresholds
    if params:
        p.update(params)
    p.setdefault("lot", LOT.get(asset, 65))
    filters = filters or {}

    df, minutes, spot_1m = load_chain(asset, expiry)
    if df is None or len(minutes) < 20:
        return [], {"error": f"no recorded option data for {asset}"}
    df5m = build_5m(spot_1m)
    from scalper_backtest import precompute as _precompute
    P = _precompute(df5m)
    enh.attach_indicators(P, p["vwap_window"], p["adx_slope_window"])
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
        # 5m bar index of this signal (no lookahead — same bar the score used)
        pos = int(df5m.index.searchsorted(sts))
        pos = min(pos, len(df5m) - 1)

        # S/R proximity filter
        if filters.get("sr"):
            if pos > 0:
                r1, s1 = sr_levels(df5m, pos)
                if sr_blocked(sig["side"], spot_at_entry, r1, s1, p["sr_buffer"]):
                    continue

        # Candidate confirmation filters — OFF by default; False blocks, None skips
        if filters.get("vwap_slope"):
            if enh.vwap_slope_ok(P, pos, sig["side"], p["vwap_window"]) is False:
                continue
        if filters.get("ema_sep_atr"):
            if enh.ema_sep_atr_ok(P, pos, sig["side"], p["ema_sep_min"]) is False:
                continue
        if filters.get("adx_dir"):
            if enh.adx_dir_ok(P, pos, sig["side"], p["adx_level"]) is False:
                continue
        if filters.get("orb_retest"):
            if enh.orb_retest_ok(P, pos, sig["side"], p["orb_tol"], p["orb_lookback"]) is False:
                continue

        # RVOL filter (chain activity at the entry minute)
        if filters.get("rvol"):
            rv = chain_activity(df, minutes[entry_idx], p["rvol_window"])
            if rv is None or rv < p["rvol_min"]:
                continue

        strike, row = _select_strike(lookup, minutes[entry_idx], sig["side"],
                                     spot_at_entry, p["delta_lo"], p["delta_hi"])
        if strike is None:
            continue
        # Option microstructure gate (fresh quote + spread + vol + OI + premium)
        if filters.get("micro"):
            if not enh.microstructure_ok(row, sig["side"], p["micro_max_spread"],
                                         p["micro_min_oi"], p["micro_min_vol"]):
                continue
        t = run_option_trade(lookup, minutes, entry_idx, sig["side"], strike, p)
        if t is None:
            continue
        t["signal_ts"] = str(sts)
        t["entry_ts"] = str(minutes[entry_idx])
        t["split"] = "train" if minutes[entry_idx] < cut else "test"
        t["score"] = sig["score"]
        trades.append(t)

    uniq = sorted({str(e) for e in df["expiry"].dropna().unique()})
    meta = {
        "asset": asset,
        "expiry": expiry or (uniq[0] if len(uniq) == 1 else f"per-day ({len(uniq)} expiries)"),
        "snapshots": len(minutes), "signals": len(sigs),
        "bars_5m": len(df5m), "trades": len(trades),
        "cut": str(cut),
    }
    return trades, meta


# ── Reporting ───────────────────────────────────────────────────────
def bootstrap_ci(nets, n_boot=2000, ci=0.95, seed=0):
    """Bootstrap confidence interval + standard error of the per-trade NET mean.

    Returns {mean, lo, hi, se} (₹/trade), or None when n < 5 (degenerate).
    Deterministic for a given seed → reproducible research.
    """
    nets = np.asarray(nets, dtype=float)
    if len(nets) < 5:
        return None
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for k in range(n_boot):
        means[k] = rng.choice(nets, size=len(nets), replace=True).mean()
    lo, hi = np.percentile(means, [100 * (1 - ci) / 2, 100 * (1 + ci) / 2])
    return {"mean": float(nets.mean()), "lo": float(lo), "hi": float(hi),
            "se": float(means.std(ddof=0))}


def _expectancy(trades):
    if not trades:
        return {"n": 0, "wr": None, "net": 0.0, "ev": None, "pf": None,
                "gw": 0.0, "gl": 0.0, "mfe": None, "mae": None, "r": None,
                "mdd": 0.0, "ci_lo": None, "ci_hi": None, "boot_se": None}
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
    # max drawdown on cumulative NET (₹) in trade order
    cum = np.cumsum(nets)
    mdd = float((cum - np.maximum.accumulate(cum)).min())
    ci = bootstrap_ci(nets)
    return {
        "n": len(trades), "wr": wr, "net": round(sum(nets), 2),
        "ev": round(float(np.mean(nets)), 2), "pf": round(pf, 2) if pf != float("inf") else None,
        "gw": round(gw, 2), "gl": round(gl, 2),
        "mfe": round(mfe, 3) if mfe is not None else None,
        "mae": round(mae, 3) if mae is not None else None,
        "r": round(mfe / mae, 2) if (mfe and mae) else None,
        "mdd": round(mdd, 2),
        "ci_lo": round(ci["lo"], 2) if ci else None,
        "ci_hi": round(ci["hi"], 2) if ci else None,
        "boot_se": round(ci["se"], 2) if ci else None,
    }


def _print(label, trades):
    e = _expectancy(trades)
    print(f"  {label:<46} n={e['n']:<3} WR={e['wr'] if e['wr'] is not None else '-':>6} "
          f"EV=₹{e['ev'] if e['ev'] is not None else 0:>7} net=₹{e['net']:>8} PF={e['pf'] if e['pf'] is not None else '-':>5}")
    return e


def _split(trades, key):
    return [t for t in trades if t["split"] == key]


# ── Ablation: baseline → each enhancement → combined ───────────────
def ablate(asset="nifty"):
    """Run the candidate enhancement filters one-by-one and combined.

    Returns [(label, all_expectancy, oos_expectancy)]. Every enhancement is OFF
    by default; this harness is the only place they are enabled, and the verdict
    (keep/reject) is decided by OOS NET expectancy — never by in-sample fit.
    """
    configs = [
        ("BASELINE", {}),
        ("+VWAP slope", {"vwap_slope": True}),
        ("+EMA sep/ATR", {"ema_sep_atr": True}),
        ("+ADX direction", {"adx_dir": True}),
        ("+ORB retest", {"orb_retest": True}),
        ("+Microstructure", {"micro": True}),
        ("+COMBINED", {"vwap_slope": True, "ema_sep_atr": True, "adx_dir": True,
                       "orb_retest": True, "micro": True}),
    ]
    out = []
    for label, flt in configs:
        trades, _meta = backtest(asset, filters=flt)
        test = _split(trades, "test") if trades else []
        out.append((label, _expectancy(trades), _expectancy(test)))
    return out


def _print_ablation(asset):
    print(f"\nAblation — {asset.upper()} (baseline → each enhancement → combined; NET ₹)")
    print("-" * 110)
    print(f"  {'config':<16} {'n':>4} {'WR':>7} {'NET EV':>9} {'PF':>6} {'maxDD':>9} "
          f"| {'OOS n':>5} {'OOS EV':>9} {'OOS 95% CI':>22}")
    for label, all_e, oos_e in ablate(asset):
        ci = (f"[{oos_e['ci_lo']},{oos_e['ci_hi']}]"
              if oos_e.get('ci_lo') is not None else "[—,—]")
        print(f"  {label:<16} {all_e['n']:>4} "
              f"{all_e['wr'] if all_e['wr'] is not None else '-':>7} "
              f"{all_e['ev'] if all_e['ev'] is not None else 0:>9} "
              f"{all_e['pf'] if all_e['pf'] is not None else '-':>6} "
              f"{all_e['mdd']:>9} "
              f"| {oos_e['n']:>5} "
              f"{oos_e['ev'] if oos_e['ev'] is not None else 0:>9} "
              f"{ci:>22}")
    print("-" * 110)
    print("NOTE: thresholds are defaults; optimize on TRAIN only, then evaluate OOS.")
    print("      A candidate is adopted only if its OOS 95% CI is entirely > 0.")


def main():
    asset = sys.argv[1] if len(sys.argv) > 1 else "nifty"
    df, minutes, spot_1m = load_chain(asset)
    if df is None:
        print(f"FAIL: no recorded option data for {asset}")
        return

    print(f"Option P&L Backtest — {asset.upper()} (recorded chain data)")
    uniq = sorted({str(e) for e in df["expiry"].dropna().unique()})
    exp_txt = uniq[0] if len(uniq) == 1 else f"{len(uniq)} weekly chains (per-day dominant)"
    print(f"  expiry {exp_txt} · {len(minutes)} 1m snapshots · "
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

    # ── 2. S/R proximity filter (SIMPLE session floor-pivot R1/S1, OOS comparison) ──
    t_sr, _ = backtest(asset, filters={"sr": True})
    print(f"\n+S/R proximity filter  (simple pivot R1/S1, buffer ±{DEFAULTS['sr_buffer']} pts)")
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

    # ── 6. RVOL threshold sensitivity (OOS comparison — do NOT assume 1.0×) ──
    print("\nRVOL threshold sensitivity (OOS only, no other filters):")
    for rv_min in (0.5, 1.0, 1.5, 2.0):
        t_rv2, _ = backtest(asset, filters={"rvol": True}, params={"rvol_min": rv_min})
        _print(f"rvol_min {rv_min:>4}×", _split(t_rv2, "test"))

    print("=" * 100)
    print("NOTE: NET expectancy is after bid/ask spread + slippage + full cost model")
    print("      (brokerage ₹20×2 + STT 0.1% + exchange + stamp + GST).")
    print("      Significance is judged by the OOS confidence interval + bootstrap SE,")
    print("      NOT by a minimum trade count. No edge is claimed while the CI spans 0.")

    # ── 7. Enhancement ablation (baseline → each → combined) ──
    _print_ablation(asset)


if __name__ == "__main__":
    main()
