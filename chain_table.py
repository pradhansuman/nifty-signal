#!/usr/bin/env python3
"""
Option Chain Table — strike-by-strike OI/IV/premium/delta for Nifty weekly expiry via Upstox.
Identifies call wall / put wall (max OI) and returns rows around ATM.
Cached 60s.
"""
import json, os, time, requests, sys
from datetime import datetime, timedelta

CACHE_TTL = 60
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
ASSETS = {
    "nifty": {"symbol": "NSE_INDEX|Nifty 50", "cache": "chain_cache.json"},
    "banknifty": {"symbol": "NSE_INDEX|Nifty Bank", "cache": "bnf_chain_cache.json"},
}
_cache = {"nifty": {"ts": 0, "data": None}, "banknifty": {"ts": 0, "data": None}}

from tomorrow_outlook import get_outlook


def _token():
    token = os.environ.get("UPSTOX_TOKEN", "")
    if not token:
        from upstox_token import get_token
        token = get_token()
    return token


def _next_tuesday():
    today = datetime.now()
    if today.weekday() == 1:  # Tuesday is the weekly expiry day → this week's chain
        return today.strftime("%Y-%m-%d")
    days = (1 - today.weekday()) % 7
    return (today + timedelta(days=days)).strftime("%Y-%m-%d")


def _monthly_last_tuesday():
    today = datetime.now()
    if today.month == 12:
        nxt = datetime(today.year + 1, 1, 1)
    else:
        nxt = datetime(today.year, today.month + 1, 1)
    last_day = nxt - timedelta(days=1)
    days_back = (last_day.weekday() - 1) % 7
    return (last_day - timedelta(days=days_back)).strftime("%Y-%m-%d")


def _find_available_expiry(token, symbol, preferred, max_scan=20):
    """Try preferred expiry, then scan forward up to max_scan days for a live series."""
    try:
        for off in range(0, max_scan):
            d = datetime.strptime(preferred, "%Y-%m-%d") + timedelta(days=off)
            exp = d.strftime("%Y-%m-%d")
            r = requests.get(
                "https://api.upstox.com/v2/option/chain",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                params={"instrument_key": symbol, "expiry_date": exp},
                timeout=12)
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    return exp, data
    except Exception:
        pass
    return preferred, None


def get_chain(force=False, strike_range=8, asset="nifty"):
    cfg = ASSETS.get(asset)
    if not cfg:
        return {"error": f"Unknown asset {asset}"}
    c = _cache.setdefault(asset, {"ts": 0, "data": None})
    now = time.time()
    if not force and c["data"] and (now - c["ts"]) < CACHE_TTL:
        return c["data"]

    out = {"error": None, "expiry": None, "atm": None, "call_wall": None, "put_wall": None,
           "call_wall_oi": 0, "put_wall_oi": 0, "rows": [], "chain_spot": None, "asset": asset}

    token = _token()
    if not token:
        out["error"] = "No Upstox token"
        return out

    expiry = _next_tuesday() if asset == "nifty" else _monthly_last_tuesday()
    out["expiry"] = expiry
    try:
        expiry, data = _find_available_expiry(token, cfg["symbol"], expiry)
        out["expiry"] = expiry
        if not data:
            out["error"] = "Empty chain"
            c["ts"], c["data"] = now, out
            return out
    except Exception as e:
        out["error"] = str(e)[:80]
        return out

    rows = []
    cw = pw = None
    cw_oi = pw_oi = 0
    for item in data:
        strike = item.get("strike_price", 0)
        ce = item.get("call_options", {}).get("market_data", {})
        pe = item.get("put_options", {}).get("market_data", {})
        cg = item.get("call_options", {}).get("option_greeks", {})
        pg = item.get("put_options", {}).get("option_greeks", {})
        row = {
            "strike": strike,
            "ce_key": item.get("call_options", {}).get("instrument_key"),
            "pe_key": item.get("put_options", {}).get("instrument_key"),
            "ce_ltp": ce.get("ltp"), "ce_oi": ce.get("oi"), "ce_vol": ce.get("volume"),
            "ce_iv": cg.get("iv"), "ce_delta": cg.get("delta"), "ce_theta": cg.get("theta"),
            "ce_bid": ce.get("bid_price"), "ce_ask": ce.get("ask_price"),
            "pe_ltp": pe.get("ltp"), "pe_oi": pe.get("oi"), "pe_vol": pe.get("volume"),
            "pe_iv": pg.get("iv"), "pe_delta": pg.get("delta"), "pe_theta": pg.get("theta"),
            "pe_bid": pe.get("bid_price"), "pe_ask": pe.get("ask_price"),
        }
        rows.append(row)
        if (row["ce_oi"] or 0) > cw_oi:
            cw_oi = row["ce_oi"] or 0
            cw = strike
        if (row["pe_oi"] or 0) > pw_oi:
            pw_oi = row["pe_oi"] or 0
            pw = strike

    # Chain spot from first row's underlying
    try:
        out["chain_spot"] = data[0].get("underlying_spot_price")
    except Exception:
        pass

    # Find ATM
    atm = None
    if out["chain_spot"]:
        atm = min(rows, key=lambda x: abs(x["strike"] - out["chain_spot"]) if x["strike"] else 1e9)["strike"]
    elif rows:
        mid = rows[len(rows) // 2]["strike"]
        atm = mid

    # Rows around ATM
    if atm:
        out["atm"] = atm
        at = sorted(rows, key=lambda x: abs(x["strike"] - atm) if x["strike"] else 1e9)[:strike_range * 2 + 1]
        out["rows"] = sorted(at, key=lambda x: x["strike"])
    else:
        out["rows"] = rows

    out["call_wall"] = cw
    out["put_wall"] = pw
    out["call_wall_oi"] = cw_oi
    out["put_wall_oi"] = pw_oi

    # GIFT Nifty context (from tomorrow outlook, 5-min cache)
    try:
        ol = get_outlook()
        out["gift_nifty"] = ol.get("gift_nifty")
        out["gift_gap_vs_spot"] = ol.get("expected_gap")
        out["gift_trend"] = ol.get("indication")
    except Exception:
        pass

        c["ts"] = now
    c["data"] = out
    try:
        with open(os.path.join(WORKSPACE, ".openclaw", "tmp", cfg["cache"]), "w") as f:
            json.dump(out, f)
    except Exception:
        pass
    return out


if __name__ == "__main__":
    d = get_chain(force=True)
    if d.get("error"):
        print("ERROR:", d["error"])
    else:
        print(f"Expiry: {d['expiry']} | Spot: {d['chain_spot']} | ATM: {d['atm']}")
        print(f"Call wall: {d['call_wall']} (OI {d['call_wall_oi']:,}) | Put wall: {d['put_wall']} (OI {d['put_wall_oi']:,})")
        for row in d["rows"][::3]:
            print(f"  {row['strike']}: CE {row['ce_ltp']} (OI {row['ce_oi']}, IV {row['ce_iv']}) | PE {row['pe_ltp']} (OI {row['pe_oi']}, IV {row['pe_iv']})")
