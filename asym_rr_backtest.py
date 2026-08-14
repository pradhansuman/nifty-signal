#!/usr/bin/env python3
"""Asymmetric R:R backtest — does widening the target relative to the stop
(target_pct > stop_pct) improve the scalper's edge, or just cut win rate?

Reuses the exact scalper scoring from scalper_backtest.py (no lookahead), but:
  - target_pct and stop_pct are set SEPARATELY (asymmetric support)
  - BTC runs 24/7 (no session window); Nifty keeps the scalp windows.

Sweeps R:R profiles (target/stop as % of entry) and reports WR / PF / net.
"""
import sys
import numpy as np
sys.path.insert(0, ".")
from scalper import get_bars, _adx
from scalper_backtest import precompute, score_at

SYMBOLS = {"nifty": "^NSEI", "btc": "BTC-USD"}
WINDOWS = [("09:20", "11:45"), ("13:30", "15:20")]


def in_window(ts, windows):
    if windows is None:
        return True  # BTC: 24/7
    hm = ts.strftime("%H:%M")
    return any(a <= hm <= b for a, b in windows)


def run_backtest(df, target_pct, stop_pct, hold_bars=3, regime_filter=True, windows=WINDOWS, gated=True, trend_min=0.8, adx_min=25):
    P = precompute(df)
    adx = _adx(df) if gated else None
    n = len(df)
    trades = []
    open_trade = None
    for i in range(45, n - 1):
        ts = df.index[i]
        if not in_window(ts, windows):
            continue
        if int(P["sess_count"].iloc[i]) < 4:
            continue
        if open_trade is not None:
            entry, side, t_pts, s_pts = open_trade[:4]
            for j in range(1, hold_bars + 1):
                if i + j >= n:
                    break
                hi = float(P["highs"].iloc[i + j])
                lo = float(P["lows"].iloc[i + j])
                if side == 1 and hi >= entry + t_pts:
                    trades.append((entry, t_pts, "TARGET")); open_trade = None; break
                if side == 1 and lo <= entry - s_pts:
                    trades.append((entry, -s_pts, "STOP")); open_trade = None; break
                if side == -1 and lo <= entry - t_pts:
                    trades.append((entry, t_pts, "TARGET")); open_trade = None; break
                if side == -1 and hi >= entry + s_pts:
                    trades.append((entry, -s_pts, "STOP")); open_trade = None; break
            if open_trade is not None:
                jj = min(hold_bars, n - 1 - i)
                if jj < 1:
                    open_trade = None; continue
                px = float(P["closes"].iloc[i + jj])
                pnl = (px - entry) if side == 1 else (entry - px)
                trades.append((entry, pnl, "TIME")); open_trade = None
            continue
        sc = score_at(P, i)
        spot = float(P["closes"].iloc[i])
        e200 = float(P["ema200"].iloc[i])
        if gated:
            # per-asset gates: trend % and ADX threshold (tunable)
            if abs(spot - e200) / e200 * 100 < trend_min:
                continue
            if float(adx.iloc[i]) < adx_min:
                continue
        entry_px = float(P["closes"].iloc[i + 1])
        if sc >= 3:
            if regime_filter and spot < e200:
                continue
            open_trade = (entry_px, 1, entry_px * target_pct, entry_px * stop_pct)
        elif sc <= -3:
            if regime_filter and spot > e200:
                continue
            open_trade = (entry_px, -1, entry_px * target_pct, entry_px * stop_pct)
    return trades


def summarize(trades, label):
    if not trades:
        print("{:60s}: no trades".format(label))
        return None
    wins = [t[1] for t in trades if t[1] > 0]
    losses = [t[1] for t in trades if t[1] <= 0]
    wr = len(wins) / len(trades)
    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")
    print("{:60s}: {:3d} trades | WR {:5.1%} | PF {:5.2f} | net {:8.1f} pts".format(
        label, len(trades), wr, pf, sum(t[1] for t in trades)))
    return dict(n=len(trades), wr=wr, pf=pf, net=sum(t[1] for t in trades))


def sweep(asset, profiles, hold_bars=3, gated=True):
    sym = SYMBOLS[asset]
    df = get_bars(asset, period="60d", interval="5m")
    if df is None or len(df) < 500:
        print("{}: FAIL not enough data".format(asset))
        return
    windows = None if asset == "btc" else WINDOWS
    print("\n=== {} ({}) — {} bars, {} sessions, hold {} bars, {} ===".format(
        asset.upper(), sym, len(df), len(set(df.index.date)), hold_bars,
        "GATED (trend>=0.8% + ADX>=25)" if gated else "UNGATED"))
    for tp, sp in profiles:
        rr = tp / sp if sp else 0
        trades = run_backtest(df, tp, sp, hold_bars, True, windows, gated)
        summarize(trades, "target {:.2f}% / stop {:.2f}% (R:R {:.2f})".format(tp * 100, sp * 100, rr))


def gate_sweep(asset, hold_bars=3, target_pct=0.005, stop_pct=0.005):
    """Sweep per-asset trend_min / adx_min thresholds to find the gate combo
    that turns the scalper profitable with a sane signal rate (~1-4/day)."""
    sym = SYMBOLS[asset]
    df = get_bars(asset, period="60d", interval="5m")
    if df is None or len(df) < 500:
        print("{}: FAIL".format(asset))
        return
    windows = None if asset == "btc" else WINDOWS
    sessions = len(set(df.index.date))
    print("\n=== {} GATE SWEEP ({} bars, {} sessions, hold {} bars, symmetric ±{:.1f}%) ===".format(
        asset.upper(), len(df), sessions, hold_bars, target_pct * 100))
    print("{:>18} | {:>6} {:>7} {:>6} {:>8} {:>8}  {:>6}".format(
        "trend_min/adx_min", "trades", "/day", "WR", "PF", "net pts", "status"))
    best = None
    for tm in (0.8, 1.0, 1.5, 2.0, 2.5, 3.0):
        for am in (25, 30, 35, 40):
            t = run_backtest(df, target_pct, stop_pct, hold_bars, True, windows, True, tm, am)
            if not t:
                continue
            wins = [x[1] for x in t if x[1] > 0]
            losses = [x[1] for x in t if x[1] <= 0]
            pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")
            wr = len(wins) / len(t)
            per_day = len(t) / sessions
            net = sum(x[1] for x in t)
            status = "✅" if (pf >= 1.2 and per_day <= 5) else ("★" if pf >= 1.0 else "")
            print("{:>8}% / {:>6}  | {:>6} {:>7.1f} {:>6.0%} {:>8.2f} {:>8.0f}  {}".format(
                tm, am, len(t), per_day, wr, pf, net, status))
            if pf >= 1.0 and 1 <= per_day <= 5:
                if best is None or pf > best[0]:
                    best = (pf, tm, am, len(t), per_day, wr, net)
    if best:
        print("\nBEST: trend>=%.1f%% + ADX>=%d → PF %.2f, %d trades (%.1f/day), WR %.0f%%, net %.0f pts" %
              (best[1], best[2], best[0], best[3], best[4], best[5] * 100, best[6]))
    else:
        print("\nNo combo hit PF>=1.0 at 1-5 trades/day — BTC 5m scalper may be unprofitable at this hold.")


if __name__ == "__main__":
    import sys as _s
    if len(_s.argv) > 1 and _s.argv[1] == "gates":
        gate_sweep("btc")
    else:
        # (target_pct, stop_pct) — symmetric baseline + asymmetric profiles
        profiles = [
            (0.005, 0.005),   # 1.0 : 1  (current BTC default)
            (0.0075, 0.005),  # 1.5 : 1
            (0.01, 0.005),    # 2.0 : 1
            (0.0087, 0.0052), # ~1.67 : 1 (user's example profile)
            (0.008, 0.004),   # 2.0 : 1 tighter stop
        ]
        for asset in ("btc", "nifty"):
            try:
                sweep(asset, profiles)
            except Exception as e:
                print("{}: ERROR {}".format(asset, e))
