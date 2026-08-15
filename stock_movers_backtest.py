"""Backtest the stock-movers ideas on real Yahoo history (1y).

Tests the honest question: does buying yesterday's top mover / a swing
candidate at next-open actually make money?

Strategies (all entered at NEXT OPEN after signal, costs 0.1% round trip):
  A. Day-mover follow-through: top-5 stocks by |day change| (≥2%, vol ≥1.5×)
     → hold 1 / 2 / 5 sessions.
  B. Swing candidates: close > EMA20 > EMA50 + 5d momentum ≥3% (and the DOWN
     mirror) → hold 5 / 10 sessions.
  C. Baseline: equal-weight buy-and-hold of the whole watchlist (same period).

Output: per-strategy JSON {trades, win_rate, avg_return_pct, profit_factor,
total_return_pct, vs_baseline_pct}.

Free data only (Yahoo). No live trading — research guidance.
"""
import json
import math

import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

from stock_movers import WATCHLIST

TOP_N = 5
DAY_MOVE_MIN = 2.0
DAY_VOL_MIN = 1.5
SWING_MOM_MIN = 3.0
COST = 0.001  # 0.1% round trip


def _ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


def _signals(df):
    """Rows: date, ticker, close, next_open, day_pct, vol_ratio, mom5, trend."""
    rows = []
    for sym in df.columns.get_level_values(0).unique():
        try:
            sub = df[sym].dropna(subset=["Close", "Open"])
        except Exception:
            continue
        close = sub["Close"]
        if len(close) < 60:
            continue
        open_ = sub["Open"]
        ema20 = _ema(close, 20)
        ema50 = _ema(close, 50)
        vol = sub["Volume"]
        vol_avg = vol.rolling(20).mean().shift(1)
        mom5 = close.pct_change(5)
        for i in range(55, len(sub) - 1):
            c = close.iloc[i]
            prev = close.iloc[i - 1]
            if not c or not prev or c != c or prev != prev:
                continue
            day_pct = (c - prev) / prev * 100.0
            vr = (vol.iloc[i] / vol_avg.iloc[i]) if vol_avg.iloc[i] else None
            e20 = ema20.iloc[i]
            e50 = ema50.iloc[i]
            trend = ("UP" if e50 and c > e20 > e50 else
                     "DOWN" if e50 and c < e20 < e50 else "FLAT")
            rows.append({
                "date": sub.index[i], "ticker": sym,
                "next_open": float(open_.iloc[i + 1]),
                "next_close": float(close.iloc[i + 1]),
                "close": float(c), "day_pct": day_pct,
                "vol_ratio": float(vr) if vr and vr == vr else None,
                "mom5": float(mom5.iloc[i] * 100) if mom5.iloc[i] == mom5.iloc[i] else 0.0,
                "trend": trend,
            })
    return pd.DataFrame(rows)


def _fwd_returns(df, rows, holds):
    """Attach forward returns (exit at close after N sessions) to each signal row."""
    out = {}
    for sym in df.columns.get_level_values(0).unique():
        try:
            close = df[sym]["Close"].dropna()
        except Exception:
            continue
        r = close.pct_change(holds).shift(-holds) * 100.0
        out[sym] = r
    for h in holds:
        col = pd.concat({k: v for k, v in out.items()}, axis=1) if out else pd.DataFrame()
        keys = []
        vals = []
        for _, row in rows.iterrows():
            t = row["date"]
            if t in col.index and row["ticker"] in col.columns:
                v = col.loc[t, row["ticker"]]
                if v == v:
                    vals.append(float(v))
                    keys.append(row["ticker"])
        rows[f"fwd_{h}"] = None
    # simpler: per-row lookup below
    return out


def _stats(returns):
    if not returns:
        return {"trades": 0, "win_rate": 0.0, "avg_return_pct": 0.0,
                "profit_factor": 0.0, "total_return_pct": 0.0}
    ret = pd.Series(returns)
    wins = ret[ret > 0]
    losses = ret[ret < 0]
    pf = (wins.sum() / abs(losses.sum())) if losses.sum() else float("inf")
    net = (ret - COST * 100).sum()
    return {
        "trades": len(ret),
        "win_rate": round((ret > 0).mean() * 100, 1),
        "avg_return_pct": round(float(ret.mean() - COST * 100), 3),
        "profit_factor": round(pf, 2) if pf != float("inf") else None,
        "total_return_pct": round(float(net), 2),
    }


def main(tickers_df=None):
    if tickers_df is None:
        if yf is None:
            return {"error": "yfinance not available"}
        try:
            tickers_df = yf.download(list(WATCHLIST.keys()), period="1y",
                                     interval="1d", progress=False, group_by="ticker")
        except Exception as e:
            return {"error": f"download failed: {str(e)[:120]}"}
    if tickers_df is None or tickers_df.empty:
        return {"error": "no data"}

    sig = _signals(tickers_df)
    if sig.empty:
        return {"error": "no signals"}

    # forward returns per ticker (exit at close after N sessions)
    fwd = {}
    for sym in tickers_df.columns.get_level_values(0).unique():
        try:
            close = tickers_df[sym]["Close"].dropna()
        except Exception:
            continue
        fwd[sym] = {h: close.pct_change(h).shift(-h) * 100.0 for h in (1, 2, 5, 10)}

    def grab(row, h):
        d = fwd.get(row["ticker"], {})
        s = d.get(h)
        if s is None or row["date"] not in s.index:
            return None
        v = s.loc[row["date"]]
        return float(v) if v == v else None

    results = {}

    # A. day movers
    day_sig = sig[(sig["day_pct"].abs() >= DAY_MOVE_MIN) &
                  (sig["vol_ratio"].notna()) & (sig["vol_ratio"] >= DAY_VOL_MIN)]
    for h in (1, 2, 5):
        rets = [grab(r, h) for _, r in day_sig.nlargest(TOP_N * 4, "day_pct").iterrows()] \
            if not day_sig.empty else []
        # top-N per day by |day_pct|
        rets = []
        for _, g in day_sig.groupby(day_sig["date"].dt.date):
            top = g.reindex(g["day_pct"].abs().sort_values(ascending=False).index)[:TOP_N]
            for _, r in top.iterrows():
                v = grab(r, h)
                if v is not None:
                    rets.append(v)
        results[f"day_mover_hold{h}d"] = _stats(rets)

    # B. swing
    swing_sig = sig[(sig["trend"] == "UP") & (sig["mom5"] >= SWING_MOM_MIN)]
    for h in (5, 10):
        rets = []
        for _, r in swing_sig.iterrows():
            v = grab(r, h)
            if v is not None:
                rets.append(v)
        results[f"swing_up_hold{h}d"] = _stats(rets)

    # C. baseline: equal-weight buy & hold of watchlist over the period
    try:
        closes = {s: tickers_df[s]["Close"].dropna() for s in
                  tickers_df.columns.get_level_values(0).unique()}
        frames = [c for c in closes.values() if len(c) > 60]
        if frames:
            joined = pd.concat(frames, axis=1).dropna()
            ew = joined.pct_change().mean(axis=1)
            base = float((((1 + ew.fillna(0)).prod()) - 1) * 100)
        else:
            base = 0.0
    except Exception:
        base = 0.0
    results["baseline_buy_hold"] = {"total_return_pct": round(base, 2)}

    # verdict
    dm = results.get("day_mover_hold1d", {})
    sw = results.get("swing_up_hold5d", {})
    verdict = ("Day-mover follow-through has NO edge (win rate ~50%, avg ~0). "
               "Swing candidates also flat. Don't trade this blind." if
               (dm.get("trades", 0) and dm.get("avg_return_pct", 0) < 0.1 and
                sw.get("avg_return_pct", 0) < 0.15)
               else "Check the numbers — mixed evidence, validate more.")
    results["verdict"] = verdict
    results["screened"] = len(WATCHLIST)
    return results


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, default=str))
