#!/usr/bin/env python3
"""
Upstox Option Chain Fetcher
Usage: python upstox_fetch.py <access_token> [expiry_date]
"""
import requests, json, sys
from datetime import datetime

UPSTOX_BASE = "https://api.upstox.com/v2"

def get_upstox_chain(access_token, symbol="NSE_INDEX|Nifty 50", expiry_date=None):
    """Fetch option chain from Upstox API."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    
    # Default expiry: next Tuesday if not specified
    if not expiry_date:
        today = datetime.now()
        days_until_tue = (1 - today.weekday()) % 7
        if days_until_tue == 0:
            days_until_tue = 7
        next_tue = today.replace(day=today.day + days_until_tue)
        expiry_date = next_tue.strftime("%Y-%m-%d")
    
    # Step 1: Get option contracts for the symbol and expiry
    params = {
        "instrument_key": symbol,
        "expiry_date": expiry_date,
    }
    
    resp = requests.get(
        f"{UPSTOX_BASE}/option/chain",
        headers=headers,
        params=params,
        timeout=30
    )
    
    if resp.status_code != 200:
        return {"error": f"Upstox API error {resp.status_code}", "detail": resp.text[:300]}
    
    data = resp.json()
    
    # Upstox returns data in a nested structure
    chain_data = data.get("data", [])
    
    # Convert to our standard format
    chain = []
    for item in chain_data:
        entry = {"strikePrice": item.get("strike_price", 0)}
        
        ce = item.get("call_options", {}) or item.get("ce", {})
        pe = item.get("put_options", {}) or item.get("pe", {})
        
        if ce:
            oi = ce.get("open_interest", 0) or 0
            entry["CE"] = {
                "openInterest": oi,
                "changeinOpenInterest": ce.get("change_in_open_interest", 0) or 0,
                "lastPrice": ce.get("last_price", 0) or 0,
                "totalTradedVolume": ce.get("volume", 0) or 0,
                "impliedVolatility": ce.get("implied_volatility", 0) or 0,
            }
        
        if pe:
            oi = pe.get("open_interest", 0) or 0
            entry["PE"] = {
                "openInterest": oi,
                "changeinOpenInterest": pe.get("change_in_open_interest", 0) or 0,
                "lastPrice": pe.get("last_price", 0) or 0,
                "totalTradedVolume": pe.get("volume", 0) or 0,
                "impliedVolatility": pe.get("implied_volatility", 0) or 0,
            }
        
        chain.append(entry)
    
    # Also get spot price
    spot = None
    try:
        spot_resp = requests.get(
            f"{UPSTOX_BASE}/market-quote/ltp",
            headers=headers,
            params={"instrument_key": "NSE_INDEX|Nifty 50"},
            timeout=10
        )
        if spot_resp.status_code == 200:
            spot_data = spot_resp.json()
            spot = spot_data.get("data", {}).get("NSE_INDEX|Nifty 50", {}).get("last_price")
    except:
        pass
    
    # Summary
    tco = sum(e.get("CE", {}).get("openInterest", 0) or 0 for e in chain)
    tpo = sum(e.get("PE", {}).get("openInterest", 0) or 0 for e in chain)
    tcv = sum(e.get("CE", {}).get("totalTradedVolume", 0) or 0 for e in chain)
    tpv = sum(e.get("PE", {}).get("totalTradedVolume", 0) or 0 for e in chain)
    
    return {
        "success": True,
        "source": "Upstox API",
        "symbol": symbol,
        "expiry": expiry_date,
        "spot": spot,
        "totalStrikes": len(chain),
        "summary": {
            "pcr_oi": round(tpo / tco, 3) if tco > 0 else None,
            "pcr_volume": round(tpv / tcv, 3) if tcv > 0 else None,
            "total_call_oi": tco,
            "total_put_oi": tpo,
            "total_call_vol": tcv,
            "total_put_vol": tpv,
        },
        "chain": chain,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python upstox_fetch.py <access_token> [expiry_date]")
        sys.exit(1)
    
    token = sys.argv[1]
    expiry = sys.argv[2] if len(sys.argv) > 2 else None
    
    result = get_upstox_chain(token, expiry_date=expiry)
    print(json.dumps(result, indent=2, default=str))
