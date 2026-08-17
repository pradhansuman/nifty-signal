#!/usr/bin/env python3
"""Backtest candidate scalper filters on top of the live gate set.

Question (2026-08-17): after a 9-short / 0-target chop day, would these help?
  - FILTER A (chop-day kill switch): after 3 same-direction TIME (expired)
    exits in one session, stop taking that direction for the rest of the session.
  - FILTER B (ADX sustained): require ADX >= gate for 2 consecutive bars
    (instead of the last bar only) before entering.

Baseline = live gates: score ±3, regime filter (spot vs 200 EMA),
trend |spot-200E| >= 0.5% of spot, ADX >= 30 (single bar). NIFTY 5m.
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, ".")
import scalper_backtest as sb
from scalper import get_bars, _adx

SYMBOL = "^NSEI"
TARGET_PCT = 0.0008   # spot points ≈ ±10% premium on ATM
HOLD_BARS = 6         # 30 min on 5m bars (live hold)
TREND_MIN = 0.5       # |spot-200E| % gate
ADX_MIN = 30.0
CHOP_KILL = 3         # consecutive same-dir TIME exits → stand down


def precompute_plus(df):
    P = sb.precompute(df)
    P["adx"] = _adx(df)
    P["trend_dist"] = (P["closes"] - P["ema200"]).abs() / P["ema200"] * 100.0
    return P


def run_variant(df, chop_kill=False, adx_sustain=1):
    P = precompute_plus(df)
    n = len(df)
    trades = []
    open_trade = None
    # per-session chop counters keyed by date → direction
    chop = {}  # date -> {dir: count}
    for i in range(45, n - 1):
        ts = df.index[i]
        if not sb.in_window(ts):
            continue
        if int(P["sess_count"].iloc[i]) < 4:
            continue
        # manage open trade
        if open_trade is not None:
            entry, side, t_pts, s_pts, entry_bar = open_trade
            done = False
            for j in range(1, HOLD_BARS + 1):
                if i + j >= n:
                    break
                hi = float(P["highs"].iloc[i + j])
                lo = float(P["lows"].iloc[i + j])
                if side == 1 and hi >= entry + t_pts:
                    trades.append((entry, t_pts, entry_bar, i + j, "TARGET", side, ts.date()))
                    open_trade = None; done = True; break
                if side == 1 and lo <= entry - s_pts:
                    trades.append((entry, -s_pts, entry_bar, i + j, "STOP", side, ts.date()))
                    open_trade = None; done = True; break
                if side == -1 and lo <= entry - t_pts:
                    trades.append((entry, t_pts, entry_bar, i + j, "TARGET", side, ts.date()))
                    open_trade = None; done = True; break
                if side == -1 and hi >= entry + s_pts:
                    trades.append((entry, -s_pts, entry_bar, i + j, "STOP", side, ts.date()))
                    open_trade = None; done = True; break
            if open_trade is not None:
                jj = min(HOLD_BARS, n - 1 - i)
                if jj < 1:
                    open_trade = None; continue
                px = float(P["closes"].iloc[i + jj])
                pnl = (px - entry) if side == 1 else (entry - px)
                trades.append((entry, pnl, entry_bar, i + jj, "TIME", side, ts.date()))
                # chop tracking (same direction only)
                if chop_kill:
                    d = ts.date()
                    chop.setdefault(d, {})[side] = chop.setdefault(d, {}).get(side, 0) + 1
                open_trade = None
            continue
        # no open trade → check entry
        sc = sb.score_at(P, i)
        spot = float(P["closes"].iloc[i])
        e200 = float(P["ema200"].iloc[i])
        side = 1 if sc >= 3 else (-1 if sc <= -3 else 0)
        if side == 0:
            continue
        # regime filter
        if (side == 1 and spot < e200) or (side == -1 and spot > e200):
            continue
        # trend gate
        if float(P["trend_dist"].iloc[i]) < TREND_MIN:
            continue
        # ADX gate (sustained = require N consecutive bars above ADX_MIN)
        adx_ok = True
        for b in range(adx_sustain):
            if i - b < 0 or float(P["adx"].iloc[i - b]) < ADX_MIN:
                adx_ok = False
                break
        if not adx_ok:
            continue
        # chop kill switch: skip this direction for the rest of the session
        if chop_kill:
            d = ts.date()
            if chop.get(d, {}).get(side, 0) >= CHOP_KILL:
                continue
        entry_px = float(P["closes"].iloc[i + 1])
        open_trade = (entry_px, side, entry_px * TARGET_PCT, entry_px * TARGET_PCT, i + 1)
    return trades


def summarize(trades, label):
    if not trades:
        print("{}: no trades".format(label))
        return None
    wins = [t[1] for t in trades if t[1] > 0]
    losses = [t[1] for t in trades if t[1] <= 0]
    wr = len(wins) / len(trades)
    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")
    from collections import Counter
    mix = Counter(t[4] for t in trades)
    net = sum(t[1] for t in trades)
    print("{:34s} {:4d} tr | WR {:4.0%} | PF {:5.2f} | net {:7.1f} pts | {}".format(
        label, len(trades), wr, pf, net, dict(mix)))
    return dict(n=len(trades), wr=wr, pf=pf, net=net, mix=dict(mix))


def main():
    df = get_bars(period="60d", interval="5m")
    if df is None or len(df) < 500:
        print("FAIL: not enough 5m data")
        return
    print("Data: {} bars, {} sessions, {} → {}".format(
        len(df), len(set(df.index.date)), df.index[0], df.index[-1]))
    print("Live gates: score ±3, regime filter, trend ≥0.5%, ADX ≥30, 30-min hold")
    print("-" * 90)
    base = run_variant(df)
    a = run_variant(df, chop_kill=True)
    b = run_variant(df, adx_sustain=2)
    ab = run_variant(df, chop_kill=True, adx_sustain=2)
    s_base = summarize(base, "BASE (live gates)")
    s_a = summarize(a, "FILTER A (chop kill ≥3)")
    s_b = summarize(b, "FILTER B (ADX sustained 2 bars)")
    s_ab = summarize(ab, "FILTER A + B")
    print("-" * 90)
    if s_base and s_a:
        print("A vs base: {} → {} trades ({}%), PF {:.2f}→{:.2f}, net {:.0f}→{:.0f}".format(
            s_base["n"], s_a["n"],
            round(100 * s_a["n"] / max(1, s_base["n"])),
            s_base["pf"], s_a["pf"], s_base["net"], s_a["net"]))
    if s_base and s_b:
        print("B vs base: {} → {} trades ({}%), PF {:.2f}→{:.2f}, net {:.0f}→{:.0f}".format(
            s_base["n"], s_b["n"],
            round(100 * s_b["n"] / max(1, s_base["n"])),
            s_base["pf"], s_b["pf"], s_base["net"], s_b["net"]))
    if s_base and s_ab:
        print("A+B vs base: {} → {} trades ({}%), PF {:.2f}→{:.2f}, net {:.0f}→{:.0f}".format(
            s_base["n"], s_ab["n"],
            round(100 * s_ab["n"] / max(1, s_base["n"])),
            s_base["pf"], s_ab["pf"], s_base["net"], s_ab["net"]))


if __name__ == "__main__":
    main()
