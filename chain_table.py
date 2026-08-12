#!/usr/bin/env python3
"""
Option Chain Table — strike-by-strike OI/IV/premium/delta for Nifty weekly expiry via Upstox.
Identifies call wall / put wall (max OI) and returns rows around ATM.
Cached 60s.
"""
import json, os, time, requests, sys
from datetime import datetime, timedelta

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "chain_cache.json")
CACHE_TTL = 60

_cache = {"ts": 0, "data": None}

from tomorrow_outlook import get_outlook


def _token():
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


def _next_tuesday():
    today = datetime.now()
    days = (1 - today.weekday()) % 7
    if days == 0:
        days = 7
    return (today + timedelta(days=days)).strftime("%Y-%m-%d")


def get_chain(force=False, strike_range=8):
    now = time.time()
    if not force and _cache["data"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    out = {"error": None, "expiry": None, "atm": None, "call_wall": None, "put_wall": None,
           "call_wall_oi": 0, "put_wall_oi": 0, "rows": [], "chain_spot": None}

    token = _token()
    if not token:
        out["error"] = "No Upstox token"
        return out

    expiry = _next_tuesday()
    out["expiry"] = expiry
    try:
        r = requests.get(
            "https://api.upstox.com/v2/option/chain",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params={"instrument_key": "NSE_INDEX|Nifty 50", "expiry_date": expiry},
            timeout=15)
        if r.status_code != 200:
            out["error"] = f"Upstox {r.status_code}"
            _cache["ts"], _cache["data"] = now, out
            return out
        data = r.json().get("data", [])
        if not data:
            out["error"] = "Empty chain"
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
            "ce_ltp": ce.get("ltp"), "ce_oi": ce.get("oi"), "ce_vol": ce.get("volume"),
            "ce_iv": cg.get("iv"), "ce_delta": cg.get("delta"),
            "pe_ltp": pe.get("ltp"), "pe_oi": pe.get("oi"), "pe_vol": pe.get("volume"),
            "pe_iv": pg.get("iv"), "pe_delta": pg.get("delta"),
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

    _cache["ts"] = now
    _cache["data"] = out
    try:
        with open(CACHE_FILE, "w") as f:
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
