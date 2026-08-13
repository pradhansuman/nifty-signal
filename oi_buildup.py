#!/usr/bin/env python3
"""
🧠 OI Buildup / Smart Money Flow strategy.

Institutions leave footprints in the options chain: when big money builds
positions, OI at specific strikes grows abnormally fast.

Logic:
- Snapshot the Nifty option chain OI every few minutes (during market hours).
- Compare current OI vs the baseline (start of the lookback window, default 60 min).
- CE buildup above spot  → institutions positioning for upside  → BUY_CALLS bias
- PE buildup below spot  → institutions positioning for downside → BUY_PUTS bias
- Net score = weighted OI growth (CE above spot − PE below spot), normalized.

Signal thresholds (score in % of total OI moved):
  score > +0.8  → BUY_CALLS (smart money loading calls)
  score < -0.8  → BUY_PUTS
  else          → WAIT (no dominant positioning)
"""
import json, os, time
from datetime import datetime

from chain_table import get_chain

WORKSPACE = os.path.dirname(os.path.abspath(__file__))
CACHE_TTL = 120
LOOKBACK_MIN = 60        # baseline window for buildup comparison
SNAPSHOT_MAX = 60        # keep ~5h of snapshots (every 5 min)
SCORE_THRESHOLD = 0.8    # % of total OI moved to trigger a signal

_cache = {"nifty": {"ts": 0, "data": None}, "banknifty": {"ts": 0, "data": None}}


def _snapshot_file(asset):
    return os.path.join(WORKSPACE, ".openclaw", "tmp", f"oi_snapshots_{asset}.json")


def _load_snapshots(asset="nifty"):
    try:
        with open(_snapshot_file(asset)) as f:
            return json.load(f)
    except Exception:
        return []


def _save_snapshots(snaps, asset="nifty"):
    os.makedirs(os.path.dirname(_snapshot_file(asset)), exist_ok=True)
    with open(_snapshot_file(asset), "w") as f:
        json.dump(snaps, f)


def take_snapshot(force=True, asset="nifty"):
    """Fetch current chain and append an OI snapshot. Returns snapshot dict."""
    chain = get_chain(force=force, asset=asset)
    if chain.get("error") or not chain.get("rows"):
        return None
    snap = {
        "ts": time.time(),
        "time": datetime.now().strftime("%H:%M"),
        "spot": chain.get("chain_spot") or chain.get("spot"),
        "asset": asset,
        "strikes": {},
    }
    for r in chain["rows"]:
        st = r["strike"]
        snap["strikes"][str(st)] = {
            "ce_oi": r.get("ce_oi") or 0,
            "pe_oi": r.get("pe_oi") or 0,
        }
    snaps = _load_snapshots(asset)
    # Don't store two snapshots in the same minute
    if snaps and snaps[-1].get("time") == snap["time"]:
        snaps[-1] = snap
    else:
        snaps.append(snap)
    if len(snaps) > SNAPSHOT_MAX:
        snaps = snaps[-SNAPSHOT_MAX:]
    _save_snapshots(snaps, asset)
    return snap


def _buildup(current, baseline):
    """Compute per-strike OI change and buildup aggregates."""
    spot = current.get("spot") or 0
    cur, base = current["strikes"], baseline["strikes"]
    strikes = set(cur) | set(base)

    ce_rows, pe_rows = [], []
    ce_sum = pe_sum = 0.0
    total_oi = 0
    for s in strikes:
        c = cur.get(s, {})
        b = base.get(s, {})
        ce_o = c.get("ce_oi") or 0
        pe_o = c.get("pe_oi") or 0
        ce_b = b.get("ce_oi") or 0
        pe_b = b.get("pe_oi") or 0
        total_oi += ce_o + pe_o
        try:
            st = int(s)
        except Exception:
            continue
        if st >= spot and ce_o > ce_b and ce_b >= 0:
            d = ce_o - ce_b
            ce_sum += d
            ce_rows.append({"strike": st, "oi_gain": d, "oi_pct": round(d / (ce_b + 1) * 100, 1)})
        if st <= spot and pe_o > pe_b and pe_b >= 0:
            d = pe_o - pe_b
            pe_sum += d
            pe_rows.append({"strike": st, "oi_gain": d, "oi_pct": round(d / (pe_b + 1) * 100, 1)})

    ce_rows.sort(key=lambda x: -x["oi_gain"])
    pe_rows.sort(key=lambda x: -x["oi_gain"])
    score = round((ce_sum - pe_sum) / (total_oi + 1) * 100, 2)  # % of total OI moved
    return {
        "ce_buildup": ce_rows[:5],
        "pe_buildup": pe_rows[:5],
        "ce_sum": int(ce_sum),
        "pe_sum": int(pe_sum),
        "score": score,
    }


def get_oi_buildup(force=False, asset="nifty"):
    """Return current OI buildup signal (cached 2 min)."""
    c = _cache.setdefault(asset, {"ts": 0, "data": None})
    now = time.time()
    if not force and c["data"] and (now - c["ts"]) < CACHE_TTL:
        return c["data"]

    snaps = _load_snapshots(asset)
    out = {"error": None, "signal": "WAIT", "bias": "NEUTRAL", "score": 0,
           "ce_buildup": [], "pe_buildup": [], "spot": None,
           "baseline_time": None, "current_time": None, "asset": asset}

    if len(snaps) < 2:
        out["error"] = "Collecting OI snapshots… (need 2 samples, ~10 min)"
        c["ts"], c["data"] = now, out
        return out

    current = snaps[-1]
    # baseline = oldest snapshot within lookback window
    cutoff = current["ts"] - LOOKBACK_MIN * 60
    baseline = snaps[0]
    for s in snaps:
        if s["ts"] >= cutoff:
            baseline = s
            break

    out["spot"] = current.get("spot")
    out["baseline_time"] = baseline.get("time")
    out["current_time"] = current.get("time")

    b = _buildup(current, baseline)
    out["score"] = b["score"]
    out["ce_buildup"] = b["ce_buildup"]
    out["pe_buildup"] = b["pe_buildup"]
    out["ce_sum"] = b["ce_sum"]
    out["pe_sum"] = b["pe_sum"]

    if b["score"] >= SCORE_THRESHOLD:
        out["signal"] = "BUY_CALLS"
        out["bias"] = "BULLISH"
    elif b["score"] <= -SCORE_THRESHOLD:
        out["signal"] = "BUY_PUTS"
        out["bias"] = "BEARISH"
    out["reason"] = (
        f"CE buildup +{b['ce_sum']:,} OI vs PE +{b['pe_sum']:,} OI "
        f"(last {LOOKBACK_MIN} min) → score {b['score']:+.2f}% of total OI"
    )
    c["ts"], c["data"] = now, out
    return out


if __name__ == "__main__":
    s = take_snapshot(force=True)
    print("snapshot:", s["time"], "spot", s["spot"], "strikes", len(s["strikes"]))
    d = get_oi_buildup(force=True)
    print(json.dumps(d, indent=1, default=str)[:900])
