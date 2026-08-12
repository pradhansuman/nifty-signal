#!/usr/bin/env python3
"""
Tomorrow Outlook — predicts next session using overnight futures.
- GIFT Nifty (SGX Nifty) via Upstox: live 24/7 overnight futures = best predictor of tomorrow's open
- US markets (S&P/Nasdaq/Dow) via Yahoo: closed overnight our time
- VIX via Yahoo
Cached 5 min (GIFT Nifty moves continuously).
"""
import json, os, sys, time, requests
from datetime import datetime
import yfinance as yf

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "outlook_cache.json")
CACHE_TTL = 300  # 5 minutes

_cache = {"ts": 0, "data": None}


def _upstox_token():
    token = os.environ.get("UPSTOX_TOKEN", "")
    if not token:
        cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "upstox_config.py")
        if os.path.exists(cfg):
            import importlib.util
            spec = importlib.util.spec_from_file_location("upstox_config", cfg)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            token = getattr(m, "UPSTOX_ACCESS_TOKEN", "")
    return token


def _gift_nifty():
    token = _upstox_token()
    if not token:
        return None
    try:
        r = requests.get(
            "https://api.upstox.com/v2/market-quote/quotes",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params={"instrument_key": "GLOBAL_INDEX|SGX NIFTY"}, timeout=10)
        if r.status_code == 200:
            for v in r.json().get("data", {}).values():
                return v.get("last_price")
    except Exception:
        pass
    return None


def get_outlook(force=False):
    now = time.time()
    if not force and _cache["data"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    out = {"error": None, "gift_nifty": None, "nifty_prev_close": None,
           "expected_gap": None, "expected_gap_pct": None, "us": {},
           "vix": None, "indication": "unknown", "read": "Data unavailable"}

    try:
        # GIFT Nifty via Upstox
        out["gift_nifty"] = _gift_nifty()

        # Nifty prev close + VIX via Yahoo
        nifty = yf.Ticker("^NSEI").fast_info
        out["nifty_prev_close"] = getattr(nifty, "previous_close", None) or getattr(nifty, "regular_market_previous_close", None)
        vix = yf.Ticker("^INDIAVIX").fast_info
        out["vix"] = getattr(vix, "last_price", None)

        # US markets
        for sym, name in [("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^DJI", "Dow")]:
            try:
                fi = yf.Ticker(sym).fast_info
                last = getattr(fi, "last_price", None)
                pc = getattr(fi, "previous_close", None) or getattr(fi, "regular_market_previous_close", None)
                if last and pc:
                    out["us"][name] = {"last": round(last, 1), "change_pct": round((last - pc) / pc * 100, 2)}
            except Exception:
                pass
    except Exception as e:
        out["error"] = str(e)[:100]

    # Expected gap
    if out["gift_nifty"] and out["nifty_prev_close"]:
        gap = out["gift_nifty"] - out["nifty_prev_close"]
        out["expected_gap"] = round(gap, 1)
        out["expected_gap_pct"] = round(gap / out["nifty_prev_close"] * 100, 2)
        if gap > 15:
            out["indication"] = "gap_up"
        elif gap < -15:
            out["indication"] = "gap_down"
        else:
            out["indication"] = "flat"

    # Read
    reads = []
    if out["expected_gap_pct"] is not None:
        g = out["expected_gap_pct"]
        if g > 0.3: reads.append(f"GIFT Nifty +{g}% → bullish open expected")
        elif g < -0.3: reads.append(f"GIFT Nifty {g}% → bearish open expected")
        else: reads.append("GIFT Nifty flat → neutral open")
    for name, u in out.get("us", {}).items():
        cp = u.get("change_pct")
        if cp is not None:
            emoji = "🟢" if cp >= 0 else "🔴"
            reads.append(f"{emoji} {name} {cp:+.2f}%")
    if out["vix"] is not None:
        if out["vix"] > 20: reads.append(f"⚠️ VIX {out['vix']:.1f} — fear elevated, premiums rich")
        elif out["vix"] < 12: reads.append(f"VIX {out['vix']:.1f} — calm, premiums cheap")
    if out["indication"] == "gap_up" and any(u.get("change_pct", 0) < -0.5 for u in out.get("us", {}).values()):
        reads.append("⚠️ Divergence: GIFT up but US closed negative — be cautious")

    if reads:
        out["read"] = " | ".join(reads)

    _cache["ts"] = now
    _cache["data"] = out
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(out, f)
    except Exception:
        pass
    return out


if __name__ == "__main__":
    print(json.dumps(get_outlook(force=True), indent=1))
