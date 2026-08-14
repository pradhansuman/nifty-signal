#!/usr/bin/env python3
"""
IV Rank / Percentile for Nifty — uses India VIX history (30-day Nifty implied vol).
- IV Rank: where current IV sits between 52-week low and high (0-100)
- IV Percentile: % of days in last year where IV was BELOW current
For option BUYERS: low rank = cheap premiums (good to buy), high rank = rich premiums (avoid).
Cached 30 min.
"""
import json, os, time
import yfinance as yf
import pandas as pd

CACHE_TTL = 1800
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
_cache = {"nifty": {"ts": 0, "data": None}, "banknifty": {"ts": 0, "data": None}}


def _atm_iv(asset):
    """ATM IV from the asset's option chain (Nifty has no ATM-IV endpoint either)."""
    try:
        from chain_table import get_chain
        d = get_chain(force=False, asset=asset)
        atm = d.get("atm")
        for r in d.get("rows", []):
            if r.get("strike") == atm:
                ce_iv = r.get("ce_iv") or r.get("pe_iv")
                return ce_iv if ce_iv else None
    except Exception:
        pass
    return None


def get_iv_rank(force=False, asset="nifty"):
    c = _cache.setdefault(asset, {"ts": 0, "data": None})
    now = time.time()
    if not force and c["data"] and (now - c["ts"]) < CACHE_TTL:
        return c["data"]

    out = {"error": None, "current_vix": None, "high_52w": None, "low_52w": None,
           "iv_rank": None, "iv_percentile": None, "read": "Data unavailable", "asset": asset,
           "atm_iv": None, "note": ""}

    try:
        hist = yf.Ticker("^INDIAVIX").history(period="1y", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            out["error"] = "No VIX history"
            c["ts"], c["data"] = now, out
            return out

        if hasattr(hist.columns, "levels") and len(hist.columns.levels) > 1:
            hist.columns = hist.columns.get_level_values(0)

        closes = hist["Close"].dropna()
        if len(closes) < 60:
            out["error"] = "Insufficient VIX history"
            c["ts"], c["data"] = now, out
            return out

        current = float(closes.iloc[-1])
        high = float(closes.max())
        low = float(closes.min())

        if asset == "banknifty":
            # BNF has no own VIX — use market VIX rank as context + BNF ATM IV
            out["atm_iv"] = _atm_iv("banknifty")
            out["note"] = "BNF uses India VIX as market-wide proxy (no BNF-specific VIX)."
        else:
            out["atm_iv"] = _atm_iv("nifty")
        # IV Rank
        rank = round((current - low) / (high - low) * 100, 1) if high > low else None
        # IV Percentile
        percentile = round((closes < current).mean() * 100, 1)

        out.update({
            "current_vix": round(current, 2),
            "high_52w": round(high, 2),
            "low_52w": round(low, 2),
            "iv_rank": rank,
            "iv_percentile": percentile,
        })

        # Read
        if rank is not None:
            if rank <= 20:
                out["read"] = f"IV Rank {rank}% — premiums CHEAP. Great time to BUY options (low IV = low premium)."
            elif rank <= 40:
                out["read"] = f"IV Rank {rank}% — premiums below average. Favourable for buyers."
            elif rank <= 60:
                out["read"] = f"IV Rank {rank}% — premiums neutral. Normal conditions."
            elif rank <= 80:
                out["read"] = f"IV Rank {rank}% — premiums elevated. Be selective buying; expect IV crush."
            else:
                out["read"] = f"IV Rank {rank}% — premiums RICH. Avoid buying; sellers have the edge."
    except Exception as e:
        out["error"] = str(e)[:100]

    c["ts"] = now
    c["data"] = out
    try:
        with open(os.path.join(WORKSPACE, ".openclaw", "tmp", f"ivrank_{asset}_cache.json"), "w") as f:
            json.dump(out, f)
    except Exception:
        pass
    return out


if __name__ == "__main__":
    print(json.dumps(get_iv_rank(force=True), indent=1))
