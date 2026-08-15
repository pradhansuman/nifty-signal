"""Indian stock movers — day-trade + swing screening on NIFTY 50 liquid names.

Free data (Yahoo Finance, batch download):
  - Daily bars 3mo  -> trend, ATR, RSI, EMA20/50, volume vs avg
  - Today's bar     -> day change % (last vs prev close)

Output for each candidate:
  - day trade: direction, day move %, vol ratio, intraday target price + %, timeline "today"
  - swing:      trend direction, 5d momentum, swing target (2×ATR) + %, timeline "5–10 sessions"

No keys required. Offline-testable: main(tickers_df=...) accepts a synthetic frame.
"""
import math

import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

# Liquid NIFTY-50 names (Yahoo .NS symbols). ~40 to keep batch fetch fast.
WATCHLIST = {
    "RELIANCE.NS": "Reliance", "TCS.NS": "TCS", "HDFCBANK.NS": "HDFC Bank",
    "ICICIBANK.NS": "ICICI Bank", "INFY.NS": "Infosys", "HINDUNILVR.NS": "HUL",
    "ITC.NS": "ITC", "SBIN.NS": "SBI", "BHARTIARTL.NS": "Airtel",
    "KOTAKBANK.NS": "Kotak Bank", "LT.NS": "L&T", "AXISBANK.NS": "Axis Bank",
    "BAJFINANCE.NS": "Bajaj Fin", "MARUTI.NS": "Maruti", "SUNPHARMA.NS": "Sun Pharma",
    "TITAN.NS": "Titan", "ASIANPAINT.NS": "Asian Paints", "ULTRACEMCO.NS": "UltraTech",
    "NTPC.NS": "NTPC", "POWERGRID.NS": "Power Grid", "ONGC.NS": "ONGC",
    "COALINDIA.NS": "Coal India", "ADANIENT.NS": "Adani Ent", "ADANIPORTS.NS": "Adani Ports",
    "WIPRO.NS": "Wipro", "HCLTECH.NS": "HCL Tech", "TECHM.NS": "Tech Mahindra",
    "INDUSINDBK.NS": "IndusInd", "HINDALCO.NS": "Hindalco", "JSWSTEEL.NS": "JSW Steel",
    "TATASTEEL.NS": "Tata Steel", "M&M.NS": "M&M",
    "BAJAJ-AUTO.NS": "Bajaj Auto", "BAJAJFINSV.NS": "Bajaj Finserv",
    "DRREDDY.NS": "Dr Reddy's", "CIPLA.NS": "Cipla", "APOLLOHOSP.NS": "Apollo Hosp",
    "DIVISLAB.NS": "Divi's", "GRASIM.NS": "Grasim", "HEROMOTOCO.NS": "Hero Moto",
    "NESTLEIND.NS": "Nestle", "BRITANNIA.NS": "Britannia", "EICHERMOT.NS": "Eicher",
    "SBILIFE.NS": "SBI Life", "HDFCLIFE.NS": "HDFC Life", "TATACONSUM.NS": "Tata Cons",
    "UPL.NS": "UPL", "DLF.NS": "DLF", "BPCL.NS": "BPCL",
}

# Screening thresholds
DAY_MOVE_MIN = 1.2      # |day change %| to be a "significant" mover
DAY_VOL_MIN = 1.4       # today volume / 20d avg volume
SWING_MOM_MIN = 3.0     # 5-session momentum % for swing candidates
SWING_ATR_MULT = 2.0    # expected swing move = 2× ATR(14)
DAY_ATR_MULT = 0.5      # intraday continuation target = 0.5× ATR(14)
MAX_DAY = 10            # rows per perspective


def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _atr(high, low, close, period=14):
    tr = pd.concat([high - low,
                    (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _analyze_ticker(sym, name, df):
    """Return a row dict for one ticker, or None if data is unusable."""
    try:
        close = df["Close"].dropna()
        if len(close) < 25:
            return None
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        if not last or not prev or last != last or prev != prev:
            return None
        day_pct = (last - prev) / prev * 100.0

        high, low = df["High"], df["Low"]
        vol = df["Volume"] if "Volume" in df else pd.Series(dtype=float)
        atr14 = float(_atr(high, low, close).iloc[-1]) or 0.0

        ema20 = float(_ema(close, 20).iloc[-1])
        ema50 = float(_ema(close, 50).iloc[-1]) if len(close) >= 50 else None
        rsi14 = float(_rsi(close).iloc[-1]) if len(close) >= 20 else None

        mom5 = 0.0
        if len(close) >= 6:
            c5 = float(close.iloc[-6])
            if c5:
                mom5 = (last - c5) / c5 * 100.0

        vol_ratio = None
        if vol.notna().sum() > 21:
            v_avg = float(vol.iloc[-21:-1].mean())
            v_last = float(vol.iloc[-1]) or 0.0
            if v_avg > 0:
                vol_ratio = v_last / v_avg

        return {
            "symbol": sym.replace(".NS", ""), "name": name, "price": round(last, 2),
            "day_pct": round(day_pct, 2), "vol_ratio": round(vol_ratio, 2) if vol_ratio else None,
            "mom5": round(mom5, 2), "atr": round(atr14, 2),
            "ema20": round(ema20, 2), "ema50": round(ema50, 2) if ema50 else None,
            "rsi": round(rsi14, 1) if rsi14 else None,
            "trend": ("UP" if ema50 and last > ema20 > ema50 else
                      "DOWN" if ema50 and last < ema20 < ema50 else "FLAT"),
        }
    except Exception:
        return None


def _day_target(r, dir_sign):
    """Intraday continuation target: last + dir_sign × 0.5×ATR. Returns (price, pct)."""
    tgt = r["price"] + dir_sign * DAY_ATR_MULT * r["atr"]
    pct = (tgt - r["price"]) / r["price"] * 100.0 if r["price"] else 0.0
    return round(tgt, 2), round(pct, 2)


def _swing_target(r, dir_sign):
    """Swing target over 5–10 sessions: last + dir_sign × 2×ATR. Returns (price, pct)."""
    tgt = r["price"] + dir_sign * SWING_ATR_MULT * r["atr"]
    pct = (tgt - r["price"]) / r["price"] * 100.0 if r["price"] else 0.0
    return round(tgt, 2), round(pct, 2)


def screen(rows):
    """Split analyzed rows into day-trade and swing perspectives."""
    day, swing = [], []
    for r in rows:
        # Day trade: significant move + above-average volume
        if r and r.get("day_pct") is not None and abs(r["day_pct"]) >= DAY_MOVE_MIN:
            vr = r.get("vol_ratio")
            if vr is None or vr >= DAY_VOL_MIN:
                d = 1 if r["day_pct"] > 0 else -1
                tgt, pct = _day_target(r, d)
                day.append({**r, "direction": "UP" if d > 0 else "DOWN",
                            "target": tgt, "target_pct": pct,
                            "timeline": "today (intraday)"})
        # Swing: clean trend + momentum, not over-extended
        if r and r.get("trend") in ("UP", "DOWN") and r.get("mom5") is not None:
            rsi_ok = r.get("rsi") is None or r["rsi"] != r["rsi"]  # NaN → no signal, pass
            if (r["trend"] == "UP" and r["mom5"] >= SWING_MOM_MIN and
                    (rsi_ok or r["rsi"] <= 72)):
                tgt, pct = _swing_target(r, 1)
                swing.append({**r, "direction": "UP", "target": tgt, "target_pct": pct,
                              "timeline": "5–10 sessions"})
            elif (r["trend"] == "DOWN" and r["mom5"] <= -SWING_MOM_MIN and
                  (rsi_ok or r["rsi"] >= 28)):
                tgt, pct = _swing_target(r, -1)
                swing.append({**r, "direction": "DOWN", "target": tgt, "target_pct": pct,
                              "timeline": "5–10 sessions"})
    day.sort(key=lambda x: abs(x["day_pct"]), reverse=True)
    swing.sort(key=lambda x: abs(x["mom5"]), reverse=True)
    return day[:MAX_DAY], swing[:MAX_DAY]


def main(tickers_df=None):
    """Fetch + screen. `tickers_df` injectable for offline tests."""
    if tickers_df is None:
        if yf is None:
            return {"error": "yfinance not available"}
        try:
            tickers_df = yf.download(list(WATCHLIST.keys()), period="3mo",
                                     interval="1d", progress=False, group_by="ticker")
        except Exception as e:
            return {"error": f"download failed: {str(e)[:120]}"}

    rows = []
    if tickers_df is None or tickers_df.empty:
        return {"error": "no data"}
    cols = tickers_df.columns
    if isinstance(cols, pd.MultiIndex):
        for sym in cols.get_level_values(0).unique():
            name = WATCHLIST.get(str(sym), str(sym))
            try:
                sub = tickers_df[sym]
            except Exception:
                continue
            r = _analyze_ticker(str(sym), name, sub)
            if r:
                rows.append(r)
    else:
        # single ticker fallback
        r = _analyze_ticker("STOCK", "Stock", tickers_df)
        if r:
            rows.append(r)

    if not rows:
        return {"error": "no usable quotes (weekend/holiday?)"}
    day, swing = screen(rows)
    return {
        "day_trade": day, "swing": swing,
        "screened": len(rows), "source": "Yahoo Finance",
        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(main(), indent=2, default=str))
