#!/usr/bin/env python3
"""
Option Recorder — forward-collects REAL option chain data every minute.

This is Path A for the "actual CE/PE backtest" goal. Historical intraday
option prices aren't available from the free sources (Upstox historical-candle
= 403, Yahoo has no Nifty options), so we build the dataset ourselves:

  Every minute during market hours (9:15–15:30 IST, Mon–Fri), snapshot the live
  Upstox option chain (bid/ask/ltp/OI/volume/IV/greeks for each strike around
  ATM) and append one JSONL record per (minute × strike).

After a few weeks this produces a genuine historical option-price dataset for a
real CE/PE backtest — no spot proxy.

Storage: .openclaw/tmp/option_history/{asset}/{YYYY-MM-DD}.jsonl  (append-only)
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime

import pytz

IST = pytz.timezone("Asia/Kolkata")

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    ".openclaw", "tmp", "option_history")

# asset -> record every N seconds
ASSETS = ("nifty", "bnf")
INTERVAL_SECONDS = 60

# map recorder asset key -> chain_table asset key (bnf chain is stored as banknifty)
CHAIN_ASSET = {"nifty": "nifty", "bnf": "banknifty"}

_lock = threading.Lock()
_thread = None


def _is_market_open(now=None):
    now = now or datetime.now(IST)
    if now.weekday() >= 5:
        return False
    hm = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= hm <= 15 * 60 + 30


def _path(asset, day):
    d = os.path.join(BASE, asset)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{day}.jsonl")


def snapshot(asset="nifty"):
    """Fetch the live chain and return a list of flat per-strike records."""
    import chain_table
    ch = chain_table.get_chain(force=True, asset=CHAIN_ASSET.get(asset, asset))
    if not isinstance(ch, dict) or ch.get("error"):
        return []
    ts = datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S")
    spot = ch.get("chain_spot")
    expiry = ch.get("expiry")
    recs = []
    for r in ch.get("rows") or []:
        recs.append({
            "ts": ts, "asset": asset, "spot": spot, "expiry": expiry,
            "strike": r.get("strike"),
            "ce_bid": r.get("ce_bid"), "ce_ask": r.get("ce_ask"),
            "ce_ltp": r.get("ce_ltp"), "ce_oi": r.get("ce_oi"),
            "ce_vol": r.get("ce_vol"), "ce_iv": r.get("ce_iv"),
            "ce_delta": r.get("ce_delta"),
            "pe_bid": r.get("pe_bid"), "pe_ask": r.get("pe_ask"),
            "pe_ltp": r.get("pe_ltp"), "pe_oi": r.get("pe_oi"),
            "pe_vol": r.get("pe_vol"), "pe_iv": r.get("pe_iv"),
            "pe_delta": r.get("pe_delta"),
        })
    return recs


def record(asset="nifty"):
    """Snapshot + append to today's JSONL (only during market hours)."""
    if not _is_market_open():
        return 0
    recs = snapshot(asset)
    if not recs:
        return 0
    day = datetime.now(IST).strftime("%Y-%m-%d")
    with _lock:
        with open(_path(asset, day), "a") as f:
            for r in recs:
                f.write(json.dumps(r, default=str) + "\n")
    return len(recs)


def _poller():
    while True:
        try:
            if _is_market_open():
                for a in ASSETS:
                    try:
                        record(a)
                    except Exception:
                        pass
        except Exception:
            pass
        time.sleep(INTERVAL_SECONDS)


def start():
    """Start the background recorder (idempotent)."""
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_poller, daemon=True)
        _thread.start()


def stats():
    """Return per-asset record counts + dates (for verification)."""
    out = {}
    if not os.path.isdir(BASE):
        return out
    for a in ASSETS:
        d = os.path.join(BASE, a)
        out[a] = {}
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                p = os.path.join(d, f)
                n = sum(1 for _ in open(p)) if f.endswith(".jsonl") else 0
                out[a][f.replace(".jsonl", "")] = n
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    r = record("nifty")
    print(f"recorded {r} nifty rows")
    print(json.dumps(stats(), indent=2))
