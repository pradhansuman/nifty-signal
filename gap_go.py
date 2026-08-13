#!/usr/bin/env python3
"""
⚡ Gap & Go / Gap Fade strategy.

Institutions trade the opening gap hard in the first 30-45 minutes.

Logic (window: 9:15–9:45 IST):
- gap_pct = (today open − prev close) / prev close × 100
- VWAP computed from today's 5m bars.
- GAP & GO:  gap ≥ +0.3% AND price holds ABOVE VWAP  → BUY CE (momentum continuation)
- GAP FADE:  gap ≤ −0.3% AND price stays BELOW VWAP  → BUY PE (weakness continues)
- GAP FILL:  price returns to prev close after a gap (mean reversion watch)
- Else WAIT.

Data: Yahoo 5m bars for ^NSEI (free). VWAP = Σ(typical×vol)/Σ(vol).
"""
import json, os, time
from datetime import datetime

import yfinance as yf
import pandas as pd

WORKSPACE = os.path.dirname(os.path.abspath(__file__))
CACHE_TTL = 60
GAP_MIN = 0.3          # % gap to be a tradable setup
_cached = {"ts": 0, "data": None}


def _ist_now():
    try:
        import pytz
        return datetime.now(pytz.timezone("Asia/Kolkata"))
    except Exception:
        return datetime.now()


def compute_gap_signal(force=False):
    """Compute Gap & Go / Gap Fade signal from today's 5m bars."""
    now = time.time()
    if not force and _cached["data"] and (now - _cached["ts"]) < CACHE_TTL:
        return _cached["data"]

    out = {"error": None, "signal": "WAIT", "gap_pct": None, "prev_close": None,
           "open": None, "vwap": None, "price": None, "reason": ""}
    try:
        # Today's 5m bars
        df = yf.download("^NSEI", period="2d", interval="5m", auto_adjust=False, progress=False)
        if df is None or df.empty:
            out["error"] = "No 5m data"
            _cached["ts"], _cached["data"] = now, out
            return out
        if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)

        # Prev close: last daily close before today
        daily = yf.download("^NSEI", period="5d", interval="1d", auto_adjust=False, progress=False)
        if hasattr(daily.columns, "levels") and len(daily.columns.levels) > 1:
            daily.columns = daily.columns.get_level_values(0)
        closes = daily["Close"].dropna()
        prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else float(closes.iloc[-1])

        today = df[df.index.date == df.index[-1].date()]
        if today.empty:
            out["error"] = "No bars for today yet (market may be closed)"
            _cached["ts"], _cached["data"] = now, out
            return out

        open_px = float(today["Open"].iloc[0])
        last_px = float(today["Close"].iloc[-1])
        tp = (today["High"] + today["Low"] + today["Close"]) / 3
        vol = today["Volume"].fillna(0)
        vwap = float((tp * vol).sum() / vol.sum()) if vol.sum() > 0 else open_px

        gap_pct = round((open_px - prev_close) / prev_close * 100, 2)
        out.update(gap_pct=gap_pct, prev_close=round(prev_close, 2),
                   open=round(open_px, 2), vwap=round(vwap, 2),
                   price=round(last_px, 2), time=datetime.now().strftime("%H:%M"))

        # Window check — only meaningful 9:15–9:45
        ist = _ist_now()
        in_window = (ist.hour == 9 and 15 <= ist.minute <= 45) or (ist.hour == 10 and ist.minute <= 5)

        if not in_window:
            out["signal"] = "WAIT"
            out["reason"] = f"Outside 9:15–9:45 window (now {ist.strftime('%H:%M')})"
        elif gap_pct >= GAP_MIN and last_px > vwap:
            out["signal"] = "GAP_GO_BUY"
            out["reason"] = (f"Gap +{gap_pct}% (open {open_px:,.0f} vs prev close {prev_close:,.0f}) "
                             f"holding above VWAP {vwap:,.0f} → momentum continuation")
        elif gap_pct <= -GAP_MIN and last_px < vwap:
            out["signal"] = "GAP_FADE_BUY"
            out["reason"] = (f"Gap {gap_pct}% (open {open_px:,.0f} vs prev close {prev_close:,.0f}) "
                             f"staying below VWAP {vwap:,.0f} → weakness continues")
        elif abs(gap_pct) >= GAP_MIN:
            out["signal"] = "GAP_FILL_WATCH"
            out["reason"] = (f"Gap {gap_pct:+.2f}% — watching fill toward prev close {prev_close:,.0f}")
        else:
            out["reason"] = f"Gap {gap_pct:+.2f}% — below {GAP_MIN}% threshold, no setup"
    except Exception as e:
        out["error"] = str(e)[:120]

    _cached["ts"], _cached["data"] = now, out
    return out


if __name__ == "__main__":
    print(json.dumps(compute_gap_signal(force=True), indent=1, default=str))
