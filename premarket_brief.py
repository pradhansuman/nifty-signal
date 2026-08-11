#!/usr/bin/env python3
"""
Nifty Pre-Market Brief — runs at 9:00 AM IST
Fetches overnight cues + levels + VIX status
"""
import yfinance as yf
import json, sys
from datetime import datetime, timedelta

def main():
    nifty = yf.Ticker("^NSEI"); vix_t = yf.Ticker("^INDIAVIX")
    nf = nifty.fast_info; vf = vix_t.fast_info
    
    spot = getattr(nf, "last_price", None)
    prev_close = getattr(nf, "previous_close", None) or getattr(nf, "regular_market_previous_close", None)
    vix_val = getattr(vf, "last_price", None)
    
    # US markets overnight
    spx = yf.Ticker("^GSPC"); spx_fi = spx.fast_info
    spx_close = getattr(spx_fi, "previous_close", None)
    spx_change = round((getattr(spx_fi, "last_price", 0) or 0) - (spx_close or 0), 1) if spx_close else None
    
    # SGX Nifty
    sgx = yf.Ticker("^NSEI")  # proxy
    sgx_fi = sgx.fast_info
    sgx_last = getattr(sgx_fi, "last_price", None)
    
    # Dollar index
    dxy = yf.Ticker("DX-Y.NYB"); dxy_fi = dxy.fast_info
    dxy_val = getattr(dxy_fi, "last_price", None)
    
    # FII/DII (not available via yfinance — would need NSE data)
    
    brief = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M IST"),
        "nifty": {
            "prev_close": round(prev_close, 2) if prev_close else None,
            "futures_sgx": round(sgx_last, 2) if sgx_last else None,
            "indication": "flat" if not (spot and prev_close) else (
                "gap_up" if spot > prev_close * 1.003 else (
                "gap_down" if spot < prev_close * 0.997 else "flat"))
        },
        "vix": round(vix_val, 2) if vix_val else None,
        "overnight": {
            "snp500_close": round(spx_close, 2) if spx_close else None,
            "snp500_change": spx_change,
            "dollar_index": round(dxy_val, 2) if dxy_val else None,
        },
        "key_levels": {},
        "outlook": "",
    }
    
    # Key levels from EMA (simplified — full pipeline has more)
    if prev_close:
        brief["key_levels"] = {
            "resistance": round(prev_close * 1.01, 2),
            "support": round(prev_close * 0.99, 2),
            "pivot": round(prev_close, 2),
        }
    
    # Outlook
    cues = []
    if spx_change and spx_change > 0.5: cues.append("US positive")
    elif spx_change and spx_change < -0.5: cues.append("US negative")
    if sgx_last and prev_close:
        gap = round((sgx_last - prev_close) / prev_close * 100, 2)
        if abs(gap) > 0.3: cues.append(f"SGX Nifty {gap:+.2f}%")
    if vix_val and vix_val > 18: cues.append("VIX elevated — caution")
    
    brief["outlook"] = " | ".join(cues) if cues else "No strong overnight cues"
    
    print(json.dumps(brief, indent=2))
    return brief

if __name__ == "__main__":
    main()
