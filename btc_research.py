#!/usr/bin/env python3
"""BTC profitability search — sweep higher timeframes + gate combos + hold
lengths to find a setup with a REAL edge (target: PF >= 1.2 at 1-5 trades/day).

Reuses scalper scoring (EMA9/21, VWAP, ORB, RSI, Stoch, 3-bar momentum) applied
to 15m / 1h bars, with per-timeframe gate sweeps. BTC runs 24/7 (no session
window), regime filter ON (spot vs 200EMA), symmetric ±0.5% target/stop.
"""
import sys
import numpy as np
sys.path.insert(0, ".")
from scalper import get_bars
from asym_rr_backtest import run_backtest


def test_combo(df, tm, am, hb):
    t = run_backtest(df, 0.005, 0.005, hb, True, None, True, tm, am)
    if not t:
        return None
    wins = [x[1] for x in t if x[1] > 0]
    losses = [x[1] for x in t if x[1] <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")
    wr = len(wins) / len(t)
    net = sum(x[1] for x in t)
    return dict(n=len(t), pf=pf, wr=wr, net=net)


def find_best(interval, period="90d", label=""):
    df = get_bars("btc", period=period, interval=interval)
    if df is None or len(df) < 500:
        print("{}: FAIL data".format(interval))
        return None
    sessions = len(set(df.index.date))
    print("\n=== BTC {} ({}) — {} bars, {} sessions ===".format(interval, label, len(df), sessions))
    best = None
    for tm in (0.5, 0.8, 1.0, 1.5, 2.0):
        for am in (20, 25, 30, 35):
            for hb in (2, 3, 6):
                r = test_combo(df, tm, am, hb)
                if not r:
                    continue
                per_day = r["n"] / sessions
                ok = r["pf"] >= 1.2 and 0.5 <= per_day <= 8
                flag = "✅" if ok else ("★" if r["pf"] >= 1.0 else " ")
                print("  trend {:.1f}% adx {:>2} hold {:>2} | {:>4} tr ({:>4.1f}/d) WR {:>3.0f}% PF {:>5.2f} net {:>7.0f} {}".format(
                    tm, am, hb, r["n"], per_day, r["wr"] * 100, r["pf"], r["net"], flag), flush=True)
                if r["pf"] >= 1.0 and 0.5 <= per_day <= 8:
                    if best is None or r["pf"] > best["pf"]:
                        best = dict(trend=tm, adx=am, hold=hb, **r)
    if best:
        print("BEST {}: trend {:.1f}% + adx {} + hold {} → PF {:.2f}, {:.1f}/day, WR {:.0f}%, net {:+.0f} pts".format(
            interval, best["trend"], best["adx"], best["hold"], best["pf"], best["n"] / sessions, best["wr"] * 100, best["net"]))
    else:
        print("BEST {}: no combo hit PF>=1.0 at 0.5-8/day".format(interval))
    return best


if __name__ == "__main__":
    for interval in ("15m", "1h"):
        try:
            find_best(interval)
        except Exception as e:
            print(interval, "ERROR", e)
