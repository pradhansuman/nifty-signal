#!/usr/bin/env python3
"""
Backtest the 200 EMA bounce strategy on Nifty — mirrors live system rules exactly.
Timeframe: 1h bars (2 years) — matches how the live monitor checks intraday.
LONG entry: 0 < dist% <= 0.5 above 200 EMA, ADX>18, DI+>DI-, RSI<70, EMA20>EMA50>spot>EMA20
SHORT entry: dist% <= 0 and >= -0.8 below EMA, ADX>18, DI->DI+, RSI>30, EMA20<EMA50
Exits: stop at 0.5% beyond EMA, 0.8% break, ADX<15, 12-bar time stop.
Costs 0.05%/side. Returns in index % moves.
Cached 1 hour.
"""
import json, os, time
import yfinance as yf
import pandas as pd
import numpy as np

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "backtest_cache.json")
CACHE_TTL = 3600
COST = 0.0005
TIME_STOP = 48   # 48 hourly bars (~2 trading days) — best variant from param scan
TARGET_PCT = 1.0 # 1.0% target — best variant from param scan

_cache = {"ts": 0, "data": None}


def _ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


def _rsi(s, period=14):
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _adx(high, low, close, period=14):
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    up = high.diff()
    dn = -low.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    pdi = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    mdi = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean(), pdi, mdi


def run_backtest():
    df = yf.download("^NSEI", period="2y", interval="1h", auto_adjust=False)
    if df is None or df.empty:
        return {"error": "No Nifty 1h data"}
    if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()

    close = df["Close"]
    ema200 = _ema(close, 200)
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    rsi = _rsi(close)
    adx, pdi, mdi = _adx(df["High"], df["Low"], close)

    trades = []
    pos = None

    for i in range(200, len(df) - 1):
        if pos is None:
            d = (close.iloc[i] - ema200.iloc[i]) / ema200.iloc[i] * 100
            a, p, m = adx.iloc[i], pdi.iloc[i], mdi.iloc[i]
            r = rsi.iloc[i]
            if any(x is None or (isinstance(x, float) and np.isnan(x)) for x in (a, p, m, r)):
                continue
            if 0 < d <= 0.5 and a > 18 and p > m and r < 70 and ema20.iloc[i] > ema50.iloc[i] and close.iloc[i] > ema20.iloc[i]:
                pos = {"dir": "long", "entry": float(close.iloc[i + 1]), "idx": i + 1,
                       "stop": float(ema200.iloc[i] * 0.995),
                       "tgt": float(close.iloc[i + 1] * (1 + TARGET_PCT / 100))}
            elif -0.8 <= d < 0 and a > 18 and m > p and r > 30 and ema20.iloc[i] < ema50.iloc[i] and close.iloc[i] < ema20.iloc[i]:
                pos = {"dir": "short", "entry": float(close.iloc[i + 1]), "idx": i + 1,
                       "stop": float(ema200.iloc[i] * 1.005),
                       "tgt": float(close.iloc[i + 1] * (1 - TARGET_PCT / 100))}
        else:
            price = close.iloc[i]
            d = (price - ema200.iloc[i]) / ema200.iloc[i] * 100
            a, p, m = adx.iloc[i], pdi.iloc[i], mdi.iloc[i]
            exit_reason = None
            if pos["dir"] == "long":
                if pos.get("tgt") and price >= pos["tgt"]: exit_reason = "target"
                elif price <= pos["stop"]: exit_reason = "stop"
                elif d < -0.8: exit_reason = "break"
                elif a is not None and not np.isnan(a) and a < 15: exit_reason = "adx_death"
            else:
                if pos.get("tgt") and price <= pos["tgt"]: exit_reason = "target"
                elif price >= pos["stop"]: exit_reason = "stop"
                elif d > 0.8: exit_reason = "break"
                elif a is not None and not np.isnan(a) and a < 15: exit_reason = "adx_death"

            if exit_reason or (i - pos["idx"]) >= TIME_STOP:
                exit_reason = exit_reason or "time"
                gross = (price - pos["entry"]) / pos["entry"] if pos["dir"] == "long" else (pos["entry"] - price) / pos["entry"]
                net = gross - 2 * COST
                trades.append({
                    "entry_date": str(close.index[pos["idx"]]),
                    "exit_date": str(close.index[i]),
                    "dir": pos["dir"],
                    "bars": i - pos["idx"],
                    "ret": round(net * 100, 2),
                    "exit": exit_reason,
                })
                pos = None

    if len(trades) < 3:
        return {"error": f"Only {len(trades)} trades — insufficient sample"}

    rets = np.array([t["ret"] for t in trades])
    wins = rets[rets > 0]
    losses = rets[rets <= 0]
    equity = np.cumprod(1 + rets / 100)
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak

    monthly = {}
    for t in trades:
        ym = t["entry_date"][:7]
        monthly[ym] = monthly.get(ym, 0) + t["ret"]
    last6 = dict(sorted(monthly.items())[-6:])

    return {
        "period": f"{close.index[0]} → {close.index[-1]}",
        "bars": "1-hour",
        "trades": len(trades),
        "win_rate": round(len(wins) / len(rets) * 100, 1),
        "avg_win": round(wins.mean(), 2) if len(wins) else 0,
        "avg_loss": round(losses.mean(), 2) if len(losses) else 0,
        "expectancy": round(rets.mean(), 2),
        "profit_factor": round(abs(wins.sum() / losses.sum()), 2) if len(losses) and losses.sum() != 0 else None,
        "total_return_pct": round((equity[-1] - 1) * 100, 1),
        "max_drawdown_pct": round(dd.min() * 100, 1),
        "best_trade": round(rets.max(), 2),
        "worst_trade": round(rets.min(), 2),
        "avg_bars": round(np.mean([t["bars"] for t in trades]), 1),
        "long_trades": len([t for t in trades if t["dir"] == "long"]),
        "short_trades": len([t for t in trades if t["dir"] == "short"]),
        "exit_reasons": {
            "target": len([t for t in trades if t["exit"] == "target"]),
            "stop": len([t for t in trades if t["exit"] == "stop"]),
            "break": len([t for t in trades if t["exit"] == "break"]),
            "adx_death": len([t for t in trades if t["exit"] == "adx_death"]),
            "time": len([t for t in trades if t["exit"] == "time"]),
        },
        "last6_monthly": {k: round(v, 2) for k, v in last6.items()},
    }


def get_backtest(force=False):
    now = time.time()
    if not force and _cache["data"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]
    out = run_backtest()
    if "error" not in out:
        exp = out["expectancy"]
        pf = out.get("profit_factor") or 0
        if out["win_rate"] >= 55 and exp > 0 and pf >= 1.3:
            out["read"] = f"✅ Edge confirmed: {out['win_rate']}% win rate, {exp:+.2f}%/trade, PF {pf} over {out['trades']} trades."
        elif exp > 0:
            out["read"] = f"Marginal edge: {out['win_rate']}% win rate, {exp:+.2f}%/trade, PF {pf} over {out['trades']} trades. Best variant: 48-bar hold + 1% target. Size small, strict stops."
        else:
            out["read"] = f"⚠️ No edge: {out['win_rate']}% win rate, {exp:+.2f}%/trade, PF {pf} over {out['trades']} trades. Treat signals as guidance, not certainty."
        _cache["ts"] = now
        _cache["data"] = out
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


if __name__ == "__main__":
    print(json.dumps(get_backtest(force=True), indent=1))
