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

# Decision constants (NOT significance thresholds).
#
# The verdict is driven by the OOS expectancy's confidence interval + bootstrap
# uncertainty, NOT by a minimum trade count (a 20-trade sample is still tiny).
# MIN_INFERENCE_N is only a technical floor below which a bootstrap CI is
# degenerate — it is not a claim of significance.
MIN_INFERENCE_N = 5     # below this, a bootstrap CI is meaningless
DRIFT_TOL = 0.50        # live-vs-backtest EV gap above which we call DRIFT

SCALP_PNL_HISTORY = os.path.join(HERE, ".openclaw", "tmp", "scalp_pnl_history.json")
SUMMARY_DIR = os.path.join(HERE, "research")


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

    # Expiry selection — each trading day keeps ITS OWN dominant expiry (the
    # live weekly chain actually traded that day). A single GLOBAL dominant
    # expiry silently discards every other week once the dataset spans multiple
    # expiries (chain rolls at expiry day-change).
    if expiry is not None:
        report["expiry"] = expiry
        before = len(df)
        df = df[df["expiry"] == expiry].copy()
        report["non_dominant_expiry"] = before - len(df)
    elif "expiry" in df.columns:
        day = df["ts"].dt.date
        parts, doms = [], []
        for _d, grp in df.groupby(day, sort=True):
            dom = grp["expiry"].value_counts().idxmax()
            doms.append(dom)
            parts.append(grp[grp["expiry"] == dom])
        before = len(df)
        df = pd.concat(parts).copy() if parts else df.iloc[0:0]
        report["non_dominant_expiry"] = before - len(df)
        uniq = sorted(set(doms))
        report["expiry"] = uniq[0] if len(uniq) == 1 else ", ".join(uniq)

    before = len(df)
    df = df.drop_duplicates(subset=["minute", "strike"]).sort_values(["minute", "strike"])
    report["duplicates"] = before - len(df)

    report["final"] = len(df)
    report["days"] = int(df["minute"].dt.date.nunique()) if len(df) else 0
    return df, report


# ── Stage 6: Paper Trade (live forward results) ────────────────────
# Strategy-freeze date. The freeze was declared 2026-08-18 after close, so the
# first session run entirely under the frozen code + validation loop is
# 2026-08-19. Earlier paper days ran under older, changing code (e.g. the pre-fix
# re-entry-spam scalper that lost ₹1,764 on 08-14) and would contaminate the
# live-vs-backtest comparison.
FREEZE_DATE = "2026-08-19"


def paper_stats():
    """Aggregate the live paper ledger (daily scalp P&L snapshots) → summary.

    Only days on/after FREEZE_DATE count — pre-freeze days are excluded (and
    counted separately) because they ran under old, changing scalper code.
    Returns {days, n, wins, wr, net_rs, net_pts, excluded_pre_freeze_days}.
    """
    out = {"days": 0, "n": 0, "wins": 0, "wr": 0.0, "net_rs": 0.0, "net_pts": 0.0,
           "excluded_pre_freeze_days": 0}
    if not os.path.exists(SCALP_PNL_HISTORY):
        return out
    try:
        with open(SCALP_PNL_HISTORY) as f:
            hist = json.load(f)
    except Exception:
        return out
    for d in hist:
        if str(d.get("date", "")) < FREEZE_DATE:
            out["excluded_pre_freeze_days"] += 1
            continue  # pre-freeze — not comparable evidence
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
    """Pure verdict over the loop outputs. No strategy logic.

    The decision is driven by the OOS expectancy's confidence interval and
    bootstrap uncertainty — NEVER by a minimum trade count. A 20-trade sample is
    still tiny; the CI is what tells us whether the mean is separable from zero.

    Returns {stage, reason, oos_ev, ci_lo, ci_hi, boot_se, paper_ev, gap}.
    """
    days = (clean_report or {}).get("days", 0)
    oos = oos_expectancy or {}
    oos_n = oos.get("n", 0) or 0
    oos_ev = oos.get("ev") if oos.get("ev") is not None else None
    ci_lo = oos.get("ci_lo")
    ci_hi = oos.get("ci_hi")
    boot_se = oos.get("boot_se")
    paper_n = (paper_stats_ or {}).get("n", 0) or 0
    paper_ev = ((paper_stats_ or {}).get("net_rs", 0.0) / paper_n) if paper_n else None

    res = {
        "stage": "KEEP_COLLECTING", "reason": "",
        "oos_ev": oos_ev, "ci_lo": ci_lo, "ci_hi": ci_hi, "boot_se": boot_se,
        "paper_ev": round(paper_ev, 2) if paper_ev is not None else None,
        "gap": None,
    }

    if oos_n < MIN_INFERENCE_N:
        res["reason"] = (f"OOS n={oos_n} — too few trades to compute a confidence interval "
                         f"(days={days}); keep collecting")
        return res
    if oos_ev is None or ci_lo is None or ci_hi is None:
        res["reason"] = f"OOS n={oos_n} but expectancy CI undefined — keep collecting"
        return res

    ci = f"95% CI [{ci_lo}, {ci_hi}]"

    # The CI is the gate — a CI that spans zero = insufficient evidence,
    # no matter how many trades were counted.
    if ci_hi <= 0:
        res["stage"] = "NO_EDGE_OOS"
        res["reason"] = (f"OOS NET EV ₹{oos_ev}/trade, {ci} entirely ≤ 0 "
                         f"(n={oos_n}, SE ₹{boot_se}) — no edge; baseline is the honest control")
        return res
    if ci_lo <= 0:
        res["reason"] = (f"OOS NET EV ₹{oos_ev}/trade, {ci} spans zero "
                         f"(n={oos_n}, SE ₹{boot_se}) — insufficient evidence to declare an edge; keep collecting")
        return res

    # CI entirely above zero → a tentative OOS edge. Require live paper proof.
    if paper_n < MIN_INFERENCE_N:
        res["stage"] = "PAPER_TRADE"
        res["reason"] = (f"OOS NET EV ₹{oos_ev}/trade, {ci} > 0 (n={oos_n}) — but no live "
                         f"paper sample (n={paper_n}); forward-validate on paper")
        return res

    gap = abs(paper_ev - oos_ev) / max(1.0, abs(oos_ev))
    res["gap"] = round(gap, 3)
    if gap <= DRIFT_TOL:
        res["stage"] = "EDGE_CONFIRMED"
        res["reason"] = (f"OOS {ci} > 0 AND live ₹{paper_ev:.2f}/trade ≈ backtest "
                         f"₹{oos_ev:.2f}/trade (gap {gap:.0%})")
    else:
        res["stage"] = "DRIFT"
        res["reason"] = (f"OOS {ci} > 0 but live ₹{paper_ev:.2f}/trade vs backtest "
                         f"₹{oos_ev:.2f}/trade (gap {gap:.0%}) — investigate, no strategy change")
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
    ci_txt = f"95%CI=[{oos['ci_lo']},{oos['ci_hi']}] SE=₹{oos['boot_se']}" if oos.get('ci_lo') is not None else "95%CI=[—,—]"
    print(f"[5 Walkfwd]   OOS: n={oos['n']} WR={oos['wr']} EV=₹{oos['ev']} {ci_txt} net=₹{oos['net']} "
          f"PF={oos['pf']} (ALL n={rep['oos_all']['n']} EV=₹{rep['oos_all']['ev']})")
    print(f"[6 Paper]     days={pap['days']} n={pap['n']} WR={pap['wr']:.0%} net=₹{pap['net_rs']:.0f}"
          f" (post-freeze; {pap.get('excluded_pre_freeze_days', 0)} pre-freeze day(s) excluded)")
    print(f"[7 Compare]   OOS EV ₹{rep['compare']['oos_ev']} vs paper EV ₹{rep['compare']['paper_ev']}")
    print(f"[8 DECIDE]    >>> {dec['stage']}")
    print(f"              {dec['reason']}")
    print("=" * 92)


def _write_summary(rep):
    """Persist a reproducible research output (NOT raw data) for git tracking.

    Raw option history stays local (gitignored); this small JSON carries the
    schema, health summary, clean report, expectancy + CI, paper stats, and the
    decision verdict — everything needed to audit a checkpoint.
    """
    try:
        os.makedirs(SUMMARY_DIR, exist_ok=True)
        path = os.path.join(SUMMARY_DIR, f"latest_{rep['asset']}.json")
        with open(path, "w") as f:
            json.dump(rep, f, default=str, indent=2)
    except Exception as e:
        print(f"[summary] write failed: {e}")


def main():
    asset = sys.argv[1] if len(sys.argv) > 1 else "nifty"
    rep = run(asset)
    _print(rep)
    _write_summary(rep)


if __name__ == "__main__":
    main()
