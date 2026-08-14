#!/usr/bin/env python3
"""
Delta Exchange (India) — public market-data client.

Pulls the live BTC options chain (call + put) from Delta's v2 REST API and
returns it in the SAME shape as chain_table.get_chain() so the scalper's
build_call() options path works unchanged.

No API key needed for public market data. Trading would need an API key +
secret (NOT wired — dry-run by design, matching the rest of the system).

Delta specifics:
- Symbol format: C-BTC-<strike>-<DDMMYY>  /  P-BTC-<strike>-<DDMMYY>
- contract_value = 0.001 BTC (one option = 0.001 BTC notional)
- Quotes + greeks come as strings → float
"""
import json
import os
import time
import urllib.request
from datetime import datetime

BASE = "https://api.delta.exchange"
CACHE_TTL = 30  # seconds
_cache = {"ts": 0, "data": None}
_fut_cache = {"ts": 0.0, "data": None}


def _fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _expiry_from_symbol(sym):
    """'C-BTC-65600-150826' → '15-Aug-2026' (DDMMYY)."""
    try:
        tail = sym.rsplit("-", 1)[-1]
        dt = datetime.strptime(tail, "%d%m%y")
        return dt.strftime("%d-%b-%Y")
    except Exception:
        return ""


def get_btc_futures(force=False):
    """Live BTCUSDT perpetual futures snapshot (public REST, no auth).

    Returns {price (mark), funding (8h rate), symbol, source}. Delta hides
    bid/ask/last on the public REST endpoints (websocket-only), but mark price
    + funding rate are enough for signal-level calls."""
    now = time.time()
    if not force and _fut_cache["ts"] and now - _fut_cache["ts"] < CACHE_TTL:
        return _fut_cache["data"]
    try:
        d = _fetch("{}/v2/tickers/BTCUSDT".format(BASE))
        t = d.get("result") or {}
        mark = _f(t.get("mark_price"))
        funding = _f(t.get("funding_rate"))
        data = {"price": mark, "funding": funding, "symbol": "BTCUSDT",
                "source": "delta_futures", "ts": now}
        if not mark:
            data["error"] = "no mark_price in ticker"
        _fut_cache.update({"ts": now, "data": data})
        return data
    except Exception as e:
        return {"error": str(e), "price": None, "funding": None, "source": "delta_futures"}


def get_btc_futures_candles(resolution="5m", hours=6):
    """Public BTCUSDT perpetual futures OHLCV candles → DataFrame with IST
    index, same shape as the scalper's yfinance bars (Open/High/Low/Close/
    Volume). Delta's candles API takes epoch SECONDS (ms values are rejected).

    ⚠️ DELAYED DATA: the free-tier public candles endpoint lags ~90 minutes
    (verified 2026-08-14) — NOT usable for 5m scalping indicators. Kept for
    reference/backfills only; the scalper scores on yfinance bars and uses
    get_btc_futures() (live mark) for the tradable quote."""
    import pandas as pd
    now = int(time.time())
    start = now - hours * 3600
    url = ("{}/v2/history/candles?resolution={}&symbol=BTCUSDT&start={}&end={}"
           .format(BASE, resolution, start, now))
    d = _fetch(url)
    res = d.get("result") or []
    if not res:
        return None
    rows = [{"Open": float(c["open"]), "High": float(c["high"]),
             "Low": float(c["low"]), "Close": float(c["close"]),
             "Volume": float(c.get("volume") or 0)} for c in res]
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime([c["time"] for c in res], unit="s", utc=True)\
        .tz_convert("Asia/Kolkata")
    return df


def get_btc_chain(force=False):
    """Live BTC options chain in chain_table-compatible shape.

    Returns {error, expiry, atm, rows, chain_spot, asset} where each row is
    {strike, ce_ltp, ce_bid, ce_ask, ce_delta, ce_theta,
     pe_ltp, pe_bid, pe_ask, pe_delta, pe_theta}.
    """
    now = time.time()
    if not force and _cache["data"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    out = {"error": None, "expiry": None, "atm": None, "rows": [], "chain_spot": None, "asset": "btc"}
    try:
        # Delta returns only one contract_type per query when both are requested —
        # fetch calls and puts in separate requests and merge by strike.
        ticks = []
        for ct in ("call_options", "put_options"):
            d = _fetch(
                BASE + "/v2/tickers?contract_types=" + ct + "&states=live&underlying_asset=BTC"
            )
            ticks.extend(d.get("result") or [])
        if not ticks:
            out["error"] = "No live BTC options from Delta"
            _cache.update(ts=now, data=out)
            return out

        # spot price from any ticker
        spot = None
        for t in ticks:
            sp = _f(t.get("spot_price"))
            if sp > 0:
                spot = sp
                break
        out["chain_spot"] = spot

        # group by expiry → pick the MOST LIQUID one (tightest near-ATM spread),
        # not merely the nearest — near-dated daily contracts often have wide
        # spreads that the honest spread-filter would block.
        by_exp = {}
        for t in ticks:
            exp = _expiry_from_symbol(t.get("symbol", ""))
            if not exp:
                continue
            by_exp.setdefault(exp, []).append(t)
        if not by_exp:
            out["error"] = "Could not parse expiries"
            _cache.update(ts=now, data=out)
            return out

        def _liq_score(tickers):
            spreads = []
            for t in tickers:
                st = _f(t.get("strike_price"))
                if spot and abs(st - spot) / spot > 0.03:
                    continue
                q = t.get("quotes") or {}
                bid, ask = _f(q.get("best_bid")), _f(q.get("best_ask"))
                mid = _f(t.get("mark_price")) or ((bid + ask) / 2 if ask > bid else 0)
                if ask > bid > 0 and mid > 0:
                    spreads.append((ask - bid) / mid)
            return sum(spreads) / len(spreads) if spreads else 999.0

        best_exp = min(by_exp.keys(), key=lambda e: _liq_score(by_exp[e]))
        out["expiry"] = best_exp

        strikes = {}
        for t in by_exp[best_exp]:
            strike = int(_f(t.get("strike_price")))
            if strike <= 0:
                continue
            r = strikes.setdefault(strike, {"strike": strike})
            is_call = t.get("contract_type") == "call_options"
            q = t.get("quotes") or {}
            g = t.get("greeks") or {}
            bid, ask = _f(q.get("best_bid")), _f(q.get("best_ask"))
            close = _f(t.get("close"))
            mark = _f(t.get("mark_price"))
            ltp = close if close > 0 else (mark if mark > 0 else ((bid + ask) / 2 if ask > bid else 0))
            pref = "ce" if is_call else "pe"
            r[pref + "_ltp"] = ltp
            r[pref + "_bid"] = bid
            r[pref + "_ask"] = ask
            r[pref + "_delta"] = _f(g.get("delta"))
            r[pref + "_theta"] = _f(g.get("theta"))

        rows = sorted(strikes.values(), key=lambda r: r["strike"])
        # ATM = strike nearest spot
        atm = min(rows, key=lambda r: abs(r["strike"] - spot))["strike"] if rows and spot else None
        out["rows"] = rows
        out["atm"] = atm
    except Exception as e:
        out["error"] = f"Delta fetch failed: {str(e)[:120]}"

    _cache.update(ts=now, data=out)
    return out


if __name__ == "__main__":
    c = get_btc_chain(force=True)
    print("expiry:", c["expiry"], "| spot:", c["chain_spot"], "| atm:", c["atm"], "| rows:", len(c["rows"]), "| error:", c["error"])
    for r in c["rows"][:3]:
        print("  ", r)
