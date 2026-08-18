#!/usr/bin/env python3
"""DEPRECATED as the scalper P&L backtest — superseded by option_backtest.py.

This module backtests the scalper SIGNAL EDGE on spot points (a proxy). It is
NOT a real option P&L backtest: no bid/ask, no slippage, no cost model, no
option prices. It is retained ONLY for spot-edge research (asym_rr_backtest,
btc_research, edge_research import its precompute/score_at/run_backtest).

For actual CE/PE P&L / NET expectancy, use option_backtest.py — it replays the
Option Recorder's real chain snapshots (bid/ask/LTP/OI/vol/IV/greeks) with the
full cost model, bid/ask + slippage, 1m execution, MFE/MAE, time-stop, and
walk-forward validation.

(Original method description follows, kept for the spot-edge research use.)

Method:
  - Same indicators as scalper.py (EMA9/21, fresh cross, session VWAP, 3-bar
    momentum, RSI, Stoch, ORB) computed bar-by-bar WITHOUT lookahead.
  - Entry: score >= +3 (long, spot > 200EMA) or <= -3 (short, spot < 200EMA),
    only in scalp windows (9:20-11:45, 13:30-15:20), enter NEXT bar open.
  - Exit: target or stop first within N bars (default 3 = 15 min), else close.
  - Target/stop in SPOT points ≈ ±10% premium on an ~0.8%-of-spot ATM premium
    (0.0008 x entry). Sensitivity run over 0.05%-0.12% to stay honest.
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, ".")
from scalper import get_bars, _rsi, _stoch

SYMBOL = "^NSEI"
WINDOWS = [("09:20", "11:45"), ("13:30", "15:20")]


def in_window(ts):
    hm = ts.strftime("%H:%M")
    return any(a <= hm <= b for a, b in WINDOWS)


def precompute(df):
    closes = df["Close"].astype(float)
    highs = df["High"].astype(float)
    lows = df["Low"].astype(float)
    vols = df["Volume"].fillna(0).astype(float)
    typical = (highs + lows + closes) / 3

    ema9 = closes.ewm(span=9, adjust=False).mean()
    ema21 = closes.ewm(span=21, adjust=False).mean()
    ema200 = closes.ewm(span=200, adjust=False).mean()
    rsi = _rsi(closes)
    kk, dd = _stoch(df)
    mom = closes - closes.shift(3)

    # Session-scoped expanding VWAP (no lookahead) + ORB first-3 bars
    vwap = pd.Series(np.nan, index=df.index)
    orb_high = pd.Series(np.nan, index=df.index)
    orb_low = pd.Series(np.nan, index=df.index)
    sess_count = pd.Series(0, index=df.index)
    for d, idx in df.groupby(df.index.date).groups.items():
        pos = idx
        t = typical.loc[pos]
        v = vols.loc[pos]
        if float(v.sum()) > 0:
            vw = (t * v).cumsum() / v.cumsum()
        else:
            vw = t.expanding().mean()
        vwap.loc[pos] = vw
        n = len(pos)
        oh = float(highs.loc[pos].iloc[:3].max()) if n >= 1 else np.nan
        ol = float(lows.loc[pos].iloc[:3].min()) if n >= 1 else np.nan
        orb_high.loc[pos] = oh
        orb_low.loc[pos] = ol
        sess_count.loc[pos] = np.arange(1, n + 1)
    return dict(closes=closes, highs=highs, lows=lows, ema9=ema9, ema21=ema21,
                ema200=ema200, rsi=rsi, stoch_k=kk, stoch_d=dd, mom=mom,
                vwap=vwap, orb_high=orb_high, orb_low=orb_low, sess_count=sess_count)


def score_at(P, i):
    """Exact scalper scoring at bar index i (0-based)."""
    s = 0
    e9, e21 = float(P["ema9"].iloc[i]), float(P["ema21"].iloc[i])
    spot = float(P["closes"].iloc[i])
    if e9 > e21:
        s += 2
    else:
        s -= 2
    for off in (2, 1):
        p9, p21 = float(P["ema9"].iloc[i - off - 1]), float(P["ema21"].iloc[i - off - 1])
        c9, c21 = float(P["ema9"].iloc[i - off]), float(P["ema21"].iloc[i - off])
        if p9 <= p21 and c9 > c21:
            s += 2
        if p9 >= p21 and c9 < c21:
            s -= 2
    vw = float(P["vwap"].iloc[i])
    s += 1 if spot > vw else -1
    m = float(P["mom"].iloc[i])
    s += 1 if m > 0 else -1
    r = float(P["rsi"].iloc[i])
    if r > 70:
        s -= 1
    elif r < 30:
        s += 1
    k = float(P["stoch_k"].iloc[i])
    if k > 80:
        s -= 1
    elif k < 20:
        s += 1
    if spot > float(P["orb_high"].iloc[i]):
        s += 1
    elif spot < float(P["orb_low"].iloc[i]):
        s -= 1
    return s


def run_backtest(df, target_pct=0.0008, hold_bars=3, regime_filter=True):
    P = precompute(df)
    n = len(df)
    trades = []
    open_trade = None
    for i in range(45, n - 1):
        ts = df.index[i]
        if not in_window(ts):
            continue
        if int(P["sess_count"].iloc[i]) < 4:
            continue  # ORB needs first 3 bars; skip the session open
        if open_trade is not None:
            # manage open trade
            entry, side, t_pts, s_pts, entry_bar = open_trade
            done = False
            for j in range(1, hold_bars + 1):
                if i + j >= n:
                    break
                hi = float(P["highs"].iloc[i + j])
                lo = float(P["lows"].iloc[i + j])
                if side == 1 and hi >= entry + t_pts:
                    trades.append((entry, t_pts, entry_bar, i + j, "TARGET"))
                    open_trade = None
                    done = True
                    break
                if side == 1 and lo <= entry - s_pts:
                    trades.append((entry, -s_pts, entry_bar, i + j, "STOP"))
                    open_trade = None
                    done = True
                    break
                if side == -1 and lo <= entry - t_pts:
                    trades.append((entry, t_pts, entry_bar, i + j, "TARGET"))
                    open_trade = None
                    done = True
                    break
                if side == -1 and hi >= entry + s_pts:
                    trades.append((entry, -s_pts, entry_bar, i + j, "STOP"))
                    open_trade = None
                    done = True
                    break
            if open_trade is not None:
                # time exit at last managed bar
                jj = min(hold_bars, n - 1 - i)
                if jj < 1:
                    open_trade = None
                    continue
                px = float(P["closes"].iloc[i + jj])
                pnl = (px - entry) if side == 1 else (entry - px)
                trades.append((entry, pnl, entry_bar, i + jj, "TIME"))
                open_trade = None
            continue
        # no open trade → check entry at NEXT bar open (no lookahead on fills)
        sc = score_at(P, i)
        spot = float(P["closes"].iloc[i])
        e200 = float(P["ema200"].iloc[i])
        entry_px = float(P["closes"].iloc[i + 1])
        if sc >= 3:
            if regime_filter and spot < e200:
                continue
            open_trade = (entry_px, 1, entry_px * target_pct, entry_px * target_pct, i + 1)
        elif sc <= -3:
            if regime_filter and spot > e200:
                continue
            open_trade = (entry_px, -1, entry_px * target_pct, entry_px * target_pct, i + 1)
    return trades


def summarize(trades, label):
    if not trades:
        print("{}: no trades".format(label))
        return None
    wins = [t[1] for t in trades if t[1] > 0]
    losses = [t[1] for t in trades if t[1] <= 0]
    wr = len(wins) / len(trades)
    gw = float(np.mean(wins)) if wins else 0
    gl = float(np.mean(losses)) if losses else 0
    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")
    print("{}: {} trades | WR {:.0%} | avg win {:.1f} | avg loss {:.1f} | PF {:.2f} | net {:.1f} pts".format(
        label, len(trades), wr, gw, gl, pf, sum(t[1] for t in trades)))
    return dict(n=len(trades), wr=wr, gw=gw, gl=gl, pf=pf, net=sum(t[1] for t in trades))


def main():
    df = get_bars(period="60d", interval="5m")
    if df is None or len(df) < 500:
        print("FAIL: not enough 5m data")
        return
    print("Data: {} bars, {} sessions, {} -> {}".format(
        len(df), len(set(df.index.date)), df.index[0], df.index[-1]))
    print("-" * 78)
    # Base case + sensitivity
    base = run_backtest(df, 0.0008, 3, True)
    summarize(base, "BASE  (target=stop=0.08% spot, 3-bar hold, regime filter)")
    for tp in (0.0005, 0.0012):
        summarize(run_backtest(df, tp, 3, True), "SENS  (target=stop={:.2f}%, 3-bar, filter)".format(tp * 100))
    for hb in (2, 5):
        summarize(run_backtest(df, 0.0008, hb, True), "SENS  (target=0.08%, {} bar hold, filter)".format(hb))
    summarize(run_backtest(df, 0.0008, 3, False), "SENS  (target=0.08%, 3-bar, NO regime filter)")
    print("-" * 78)
    # Best-case outcome detail for the base
    t = base or []
    if t:
        from collections import Counter
        print("Exit mix:", dict(Counter(x[4] for x in t)))
        wins = [x for x in t if x[1] > 0]
        if wins:
            w = max(wins, key=lambda x: x[1])
            print("Best win: {:.1f} pts ({} @ {})".format(w[1], w[4], df.index[w[2]]))


if __name__ == "__main__":
    main()
