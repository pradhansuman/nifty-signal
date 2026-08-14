#!/usr/bin/env python3
"""Per-asset edge search — sweep timeframe × trend gate × ADX gate × hold
to find the profitable combo for each index (Nifty/BNF/Sensex), mirroring the
BTC 1h discovery (PF 1.30).

Reuses scalper scoring via asym_rr_backtest.run_backtest (no lookahead).
Indices use session windows; BTC is 24/7. Symmetric ±0.5% spot target/stop.
Usage: edge_research.py <asset> [intervals...]
"""
import sys
sys.path.insert(0, ".")
from scalper import get_bars
from asym_rr_backtest import run_backtest, WINDOWS

ASSETS = {
    "nifty":  ("^NSEI", WINDOWS),
    "bnf":    ("^NSEBANK", WINDOWS),
    "sensex": ("^BSESN", WINDOWS),
    "btc":    ("BTC-USD", None),
}


def test_combo(df, windows, tm, am, hb):
    t = run_backtest(df, 0.005, 0.005, hb, True, windows, True, tm, am)
    if not t:
        return None
    wins = [x[1] for x in t if x[1] > 0]
    losses = [x[1] for x in t if x[1] <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")
    return dict(n=len(t), pf=pf, wr=len(wins) / len(t), net=sum(x[1] for x in t))


def find_best(asset, interval):
    sym, windows = ASSETS[asset]
    period = "90d" if interval == "1h" else "60d"
    df = get_bars(asset, period=period, interval=interval)
    if df is None or len(df) < 400:
        print("[{} {}] FAIL data ({} bars)".format(asset, interval, 0 if df is None else len(df)), flush=True)
        return None
    sessions = len(set(df.index.date))
    print("[{} {}] {} bars, {} sessions".format(asset.upper(), interval, len(df), sessions), flush=True)
    best = None
    for tm in (0.5, 0.8, 1.0, 1.5, 2.0):
        for am in (20, 25, 30):
            for hb in (2, 3, 6):
                r = test_combo(df, windows, tm, am, hb)
                if not r:
                    continue
                per_day = r["n"] / sessions
                if r["pf"] >= 1.0 and 0.3 <= per_day <= 12:
                    if best is None or r["pf"] > best["pf"]:
                        best = dict(trend=tm, adx=am, hold=hb, per_day=per_day, **r)
    if best:
        print("BEST {} {}: trend {:.1f}% + adx {} + hold {} → {} trades ({:.1f}/d) WR {:.0f}% PF {:.2f} net {:+.0f} pts".format(
            asset.upper(), interval, best["trend"], best["adx"], best["hold"],
            best["n"], best["per_day"], best["wr"] * 100, best["pf"], best["net"]), flush=True)
    else:
        print("BEST {} {}: no combo PF>=1.0 at 0.3-12/day".format(asset.upper(), interval), flush=True)
    return best


if __name__ == "__main__":
    asset = sys.argv[1] if len(sys.argv) > 1 else "nifty"
    intervals = sys.argv[2:] if len(sys.argv) > 2 else ["5m", "15m", "1h"]
    for iv in intervals:
        try:
            find_best(asset, iv)
        except Exception as e:
            print("[{} {}] ERROR {}".format(asset, iv, e), flush=True)
