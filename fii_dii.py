#!/usr/bin/env python3
"""
FII/DII Smart Money fetcher — free MrChartist API (sourced from NSE).
Cached 30 min — NSE publishes daily ~6-7 PM IST, so intraday freshness matters little.
"""
import json, os, time, requests
from datetime import datetime

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "fiidii_cache.json")
CACHE_TTL = 1800  # 30 minutes
API_URL = "https://fii-diidata.mrchartist.com/api/data"

_cache = {"ts": 0, "data": None}


def get_fiidii(force=False):
    """Return FII/DII data dict. Falls back to cache file on network failure."""
    now = time.time()
    if not force and _cache["data"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    data = None
    try:
        r = requests.get(API_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
    except Exception:
        pass

    if not data or not data.get("fii_net"):
        # Fallback: disk cache
        try:
            with open(CACHE_FILE) as f:
                data = json.load(f)
        except Exception:
            data = None

    if data:
        _cache["ts"] = now
        _cache["data"] = data
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    return data


def fiidii_summary():
    """Compact dict for dashboard."""
    d = get_fiidii()
    if not d:
        return {"error": "FII/DII data unavailable (network)"}

    fii_net = d.get("fii_net")
    dii_net = d.get("dii_net")
    score = d.get("sentiment_score")

    # Read: what does this mean for Nifty?
    read = []
    if fii_net is not None:
        if fii_net > 1000:
            read.append("FIIs buying aggressively — bullish")
        elif fii_net > 0:
            read.append("FIIs mildly buying — positive")
        elif fii_net > -1000:
            read.append("FIIs mildly selling — caution")
        else:
            read.append("FIIs selling aggressively — bearish pressure")
    if dii_net is not None:
        if dii_net > 2000:
            read.append("DIIs absorbing — support likely")
        elif dii_net < -1000:
            read.append("DIIs selling too — avoid longs")

    # Divergence: FII selling + DII buying = choppy, institutional tug-of-war
    if fii_net is not None and dii_net is not None:
        if fii_net < 0 and dii_net > 0:
            read.append("⚠️ Tug-of-war (FII sell vs DII buy) — expect chop")

    return {
        "date": d.get("date"),
        "updated": d.get("_updated_at"),
        "fii_net": fii_net,
        "fii_buy": d.get("fii_buy"),
        "fii_sell": d.get("fii_sell"),
        "dii_net": dii_net,
        "dii_buy": d.get("dii_buy"),
        "dii_sell": d.get("dii_sell"),
        "sentiment_score": score,
        "read": " | ".join(read) if read else "No clear signal",
    }


if __name__ == "__main__":
    print(json.dumps(fiidii_summary(), indent=1))
