#!/usr/bin/env python3
"""
Research loop — the validation pipeline that runs while the strategy is FROZEN.

    Collect → Health → Clean → Backtest → Walk-forward/OOS → Paper Trade
            → Compare Live vs Backtest → Decide

This module contains NO indicators and NO strategy logic. It only runs the
data/validation loop over already-frozen components:
  - Collect/Health  → option_recorder.stats() / .health()
  - Clean           → clean_dataset() (validity + dedup + single-expiry report)
  - Backtest        → option_backtest.backtest()          (NET, real bid/ask + costs)
  - Walk-forward    → chronological train/test split + RVOL sweep (OOS)
  - Paper Trade     → live paper ledger (scalp_pnl_history.json)
  - Compare         → live paper EV vs backtest OOS EV
  - Decide          → KEEP_COLLECTING / NO_EDGE_OOS / PAPER_TRADE / DRIFT / EDGE_CONFIRMED

Run:
  .openclaw/tmp/venv/bin/python3 research_loop.py            # nifty
  .openclaw/tmp/venv/bin/python3 research_loop.py bnf        # bank nifty
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import option_backtest as ob          # noqa: E402
import option_recorder                # noqa: E402
from option_recorder import BASE as RECORDER_BASE  # noqa: E402

# Decision thresholds (data sufficiency — NOT strategy parameters)
MIN_DAYS = 5        # trading days before a first read
MIN_TRADES = 20     # resolved trades before OOS/paper verdicts are meaningful
DRIFT_TOL = 0.50    # live-vs-backtest EV gap above which we call DRIFT

SCALP_PNL_HISTORY = os.path.join(HERE, ".openclaw", "tmp", "scalp_pnl_history.json")


# ── Stage 3: Clean Dataset ─────────────────────────────────────────
def clean_dataset(asset="nifty", root=None, expiry=None):
    """Load raw recorder JSONL for `asset`, apply validity + dedup + single-expiry
    cleaning, and RETURN a report of what was dropped at each step.

    Returns (df, report).  df has the same shape option_backtest.load_chain
    produces (columns: ts, minute, strike, ce_*/pe_*, spot, expiry).
    """
    root = root or RECORDER_BASE
    files = sorted(glob.glob(os.path.join(root, asset, "*.jsonl")))
    report = {
        "asset": asset, "files": len(files), "raw": 0, "parsed": 0,
        "no_ts_or_strike": 0, "no_quote": 0, "duplicates": 0,
        "non_dominant_expiry": 0, "final": 0, "days": 0, "expiry": None,
    }
    rows = []
    for f in files:
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                report["raw"] += 1
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    report["parsed"] = len(rows)
    if not rows:
        return None, report

    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].map(ob._parse_ts)
    df["minute"] = df["ts"].dt.floor("min")
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")

    before = len(df)
    df = df.dropna(subset=["minute", "strike"]).copy()
    report["no_ts_or_strike"] = before - len(df)

    # A tradeable snapshot needs at least one side's mid price.
    before = len(df)
    has_quote = df[["ce_ltp", "pe_ltp"]].apply(
        lambda r: pd.notna(r["ce_ltp"]) or pd.notna(r["pe_ltp"]), axis=1)
    df = df[has_quote].copy()
    report["no_quote"] = before - len(df)

    # Dominant expiry wins (avoids mixing contracts across a roll-over).
    if expiry is None and "expiry" in df.columns:
        expiry = df["expiry"].value_counts().idxmax()
    report["expiry"] = expiry
    if expiry is not None:
        before = len(df)
        df = df[df["expiry"] == expiry].copy()
        report["non_dominant_expiry"] = before - len(df)

    before = len(df)
    df = df.drop_duplicates(subset=["minute", "strike"]).sort_values(["minute", "strike"])
    report["duplicates"] = before - len(df)

    report["final"] = len(df)
    report["days"] = int(df["minute"].dt.date.nunique()) if len(df) else 0
    return df, report


# ── Stage 6: Paper Trade (live forward results) ────────────────────
def paper_stats():
    """Aggregate the live paper ledger (daily scalp P&L snapshots) → summary.

    Returns a dict of {days, n, wins, wr, net_rs, net_pts}. Zeros if absent.
    """
    out = {"days": 0, "n": 0, "wins": 0, "wr": 0.0, "net_rs": 0.0, "net_pts": 0.0}
    if not os.path.exists(SCALP_PNL_HISTORY):
        return out
    try:
        with open(SCALP_PNL_HISTORY) as f:
            hist = json.load(f)
    except Exception:
        return out
    for d in hist:
        out["days"] += 1
        out["n"] += int(d.get("resolved", 0) or 0)
        out["wins"] += int(d.get("wins", 0) or 0)
        out["net_rs"] += float(d.get("net_rs", 0.0) or 0.0)
        out["net_pts"] += float(d.get("net_pts", 0.0) or 0.0)
    if out["n"]:
        out["wr"] = out["wins"] / out["n"]
    return out


# ── Stage 8: Decide ────────────────────────────────────────────────
def decide(clean_report, oos_expectancy, paper_stats_, backtest_meta=None):
    """Pure verdict over the loop outputs. No strategy logic — only data
    sufficiency and validation rules.

    Returns {stage, reason, oos_ev, paper_ev, gap}.
    """
    days = (clean_report or {}).get("days", 0)
    oos = oos_expectancy or {}
    oos_n = oos.get("n", 0) or 0
    oos_ev = oos.get("ev") if oos.get("ev") is not None else None
    paper_n = (paper_stats_ or {}).get("n", 0) or 0
    paper_ev = ((paper_stats_ or {}).get("net_rs", 0.0) / paper_n) if paper_n else None

    res = {
        "stage": "KEEP_COLLECTING", "reason": "", "oos_ev": oos_ev,
        "paper_ev": round(paper_ev, 2) if paper_ev is not None else None,
        "gap": None,
    }

    if days < MIN_DAYS:
        res["reason"] = f"only {days} trading day(s) of data (< {MIN_DAYS}) — keep collecting"
        return res
    if oos_n < MIN_TRADES:
        res["reason"] = f"only {oos_n} OOS trades (< {MIN_TRADES}) — keep collecting"
        return res

    # Enough data + trades: read the OOS edge.
    if oos_ev is None:
        res["reason"] = "OOS expectancy undefined — keep collecting"
        return res
    if oos_ev <= 0:
        res["stage"] = "NO_EDGE_OOS"
        res["reason"] = f"OOS NET expectancy ₹{oos_ev}/trade ≤ 0 — edge not proven (strategy frozen)"
        return res

    # Positive OOS edge → decide by live paper evidence.
    if paper_n < MIN_TRADES:
        res["stage"] = "PAPER_TRADE"
        res["reason"] = f"OOS edge positive (₹{oos_ev}/trade) but only {paper_n} live paper trades — forward-validate"
        return res

    gap = abs(paper_ev - oos_ev) / max(1.0, abs(oos_ev))
    res["gap"] = round(gap, 3)
    if gap <= DRIFT_TOL:
        res["stage"] = "EDGE_CONFIRMED"
        res["reason"] = f"live ₹{paper_ev:.2f}/trade ≈ backtest OOS ₹{oos_ev:.2f}/trade (gap {gap:.0%})"
    else:
        res["stage"] = "DRIFT"
        res["reason"] = f"live ₹{paper_ev:.2f}/trade vs backtest ₹{oos_ev:.2f}/trade (gap {gap:.0%}) — investigate, no strategy change"
    return res


# ── Orchestrator ───────────────────────────────────────────────────
def run(asset="nifty"):
    rep = {"asset": asset}

    # 1. Collect
    rep["collect"] = option_recorder.stats()
    # 2. Health
    rep["health"] = option_recorder.health()
    # 3. Clean
    _df, rep["clean"] = clean_dataset(asset)
    # 4. Backtest
    rep["backtest_trades"], rep["backtest_meta"] = ob.backtest(asset, filters={})
    # 5. Walk-forward / OOS
    trades = rep["backtest_trades"]
    test = ob._split(trades, "test") if trades else []
    rep["oos"] = ob._expectancy(test)
    rep["oos_all"] = ob._expectancy(trades)
    # 6. Paper trade
    rep["paper"] = paper_stats()
    # 7. Compare
    rep["compare"] = {
        "oos_ev": rep["oos"].get("ev"),
        "paper_ev": round(rep["paper"]["net_rs"] / rep["paper"]["n"], 2) if rep["paper"]["n"] else None,
    }
    # 8. Decide
    rep["decide"] = decide(rep["clean"], rep["oos"], rep["paper"], rep["backtest_meta"])
    return rep


def _print(rep):
    asset = rep["asset"].upper()
    cl = rep["clean"]
    bt = rep["backtest_meta"]
    oos = rep["oos"]
    pap = rep["paper"]
    dec = rep["decide"]
    print(f"RESEARCH LOOP — {asset} (strategy FROZEN)")
    print("=" * 92)
    print(f"[1 Collect]   nifty days={list(rep['collect'].get('nifty', {}).items()) if rep['collect'] else []}")
    for a, st in rep["health"].items():
        if a == "as_of":
            continue
        print(f"[2 Health]    {a:<6} ok={st.get('ok_snapshots',0):>4} err={st.get('errors',0):>3} "
              f"gap={st.get('gap_warning')} (as_of {rep['health'].get('as_of')})")
    print(f"[3 Clean]     files={cl['files']} raw={cl['raw']} → final={cl['final']} rows, "
          f"{cl['days']} day(s), expiry={cl['expiry']}")
    print(f"              dropped: no_strike={cl['no_ts_or_strike']} no_quote={cl['no_quote']} "
          f"dups={cl['duplicates']} non_dom_expiry={cl['non_dominant_expiry']}")
    print(f"[4 Backtest]  signals={bt.get('signals', 0)} trades={bt.get('trades', 0)} "
          f"snapshots={bt.get('snapshots', 0)}")
    print(f"[5 Walkfwd]   OOS: n={oos['n']} WR={oos['wr']} EV=₹{oos['ev']} net=₹{oos['net']} "
          f"PF={oos['pf']} (ALL n={rep['oos_all']['n']} EV=₹{rep['oos_all']['ev']})")
    print(f"[6 Paper]     days={pap['days']} n={pap['n']} WR={pap['wr']:.0%} net=₹{pap['net_rs']:.0f}")
    print(f"[7 Compare]   OOS EV ₹{rep['compare']['oos_ev']} vs paper EV ₹{rep['compare']['paper_ev']}")
    print(f"[8 DECIDE]    >>> {dec['stage']}")
    print(f"              {dec['reason']}")
    print("=" * 92)


def main():
    asset = sys.argv[1] if len(sys.argv) > 1 else "nifty"
    _print(run(asset))


if __name__ == "__main__":
    main()
