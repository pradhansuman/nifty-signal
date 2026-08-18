#!/usr/bin/env python3
"""
Trade Gate — the pre-trade decision chain, as a single verdict.

Runs the user's checklist in order and returns TRADE / NO TRADE with a
step-by-step PASS/FAIL/WARN breakdown:

  MARKET DATA → DATA QUALITY → MARKET REGIME → TIME OF DAY → PRICE ACTION →
  MOMENTUM/VOLUME → VWAP/ORB → OPTIONS FILTER → LIQUIDITY → EXPECTED VALUE →
  RISK CHECK → EXECUTION COST  →  TRADE / NO TRADE

Pure function — no network. Inputs are pre-fetched dicts (from get_signal,
session_regime, scalper.main, intraday_signals). Fully testable offline.

Hard-fail steps (data, regime-for-momentum, window, momentum) block the trade.
Warn steps (liquidity, EV, cost) flag but don't block — they need manual/data checks.
"""
from __future__ import annotations

import math

from cost_model import round_trip_cost, cost_pct
from risk_engine import check_limits as risk_check_limits


def trade_gate(signal=None, regime=None, scalper=None, intraday=None, trades=None):
    """
    signal:   get_signal() dict        (spot, ema_200, distance_pct, expected_move_1sd,
                                         contrarian_signal, atm_iv, ...)
    regime:   session_regime() dict    (regime, direction, label, ...)
    scalper:  scalper.main("nifty") dict (score, window, bias, signal, call, adx, vix, ...)
    intraday: intraday_signals output  (ema, vwap, ...)

    Returns {"verdict": "TRADE"|"NO_TRADE", "confidence": ..., "reason": ...,
             "steps": [{step, status, detail}, ...], "hard_fails": [...]}
    """
    signal = signal or {}
    regime = regime or {}
    scalper = scalper or {}
    intraday = intraday or {}

    steps = []

    def add(step, status, detail):
        steps.append({"step": step, "status": status, "detail": detail})

    # ── 1. MARKET DATA ──
    spot = signal.get("spot") or scalper.get("spot")
    ema200 = signal.get("ema_200") or scalper.get("ema200")
    have_data = bool(spot and ema200)
    if have_data:
        add("MARKET DATA", "pass", f"spot {spot:,.2f} · 200 EMA {ema200:,.2f}")
    else:
        add("MARKET DATA", "fail", "no spot / 200 EMA data")

    # ── 2. DATA QUALITY ──
    # We don't have a dedicated freshness check; use error-presence + plausibility.
    if not have_data:
        add("DATA QUALITY", "fail", "no data to validate")
    elif signal.get("signal") == "ERROR" or scalper.get("asset") == "error":
        add("DATA QUALITY", "fail", "upstream returned an error")
    else:
        add("DATA QUALITY", "warn", "no explicit freshness check — verify quote is live")

    # ── 3. MARKET REGIME ──
    reg = regime.get("regime", "")
    if reg in ("TRENDING", "TRANSITION"):
        add("MARKET REGIME", "pass", f"{regime.get('label')} — momentum scalp allowed")
    elif reg in ("CHOPPY", "RANGE"):
        add("MARKET REGIME", "fail", f"{regime.get('label')} — no momentum scalp; VWAP-reversion only")
    else:
        add("MARKET REGIME", "warn", "regime unknown")

    # ── 4. TIME OF DAY ──
    win = scalper.get("window", "")
    if win == "BLOCKED":
        add("TIME OF DAY", "fail", scalper.get("window_reason") or "outside scalp window")
    elif win:
        add("TIME OF DAY", "pass", f"window {win}")
    else:
        add("TIME OF DAY", "warn", "window unknown")

    # ── 5. PRICE ACTION ──
    dist = signal.get("distance_pct")
    if dist is not None:
        if abs(dist) <= 1.0:
            add("PRICE ACTION", "pass", f"spot {dist:+.2f}% vs 200 EMA — inside entry zone")
        else:
            add("PRICE ACTION", "warn", f"spot {dist:+.2f}% vs 200 EMA — extended, wait for pullback")
    else:
        add("PRICE ACTION", "warn", "no 200 EMA distance")

    # ── 6. MOMENTUM / VOLUME ──
    score = scalper.get("score")
    smin = scalper.get("score_min", 3.0)
    if score is None:
        add("MOMENTUM/VOLUME", "fail", "no momentum score")
    elif abs(score) >= smin:
        add("MOMENTUM/VOLUME", "pass", f"score {score} ≥ ±{smin} — momentum present")
    else:
        add("MOMENTUM/VOLUME", "fail", f"score {score} < ±{smin} — no edge in this chop")

    # ── 7. VWAP / ORB ──
    vwap = scalper.get("vwap") or (intraday.get("vwap") or {}).get("vwap")
    orb_hi, orb_lo = scalper.get("orb_high"), scalper.get("orb_low")
    if vwap:
        pos = "above" if spot >= vwap else "below"
        note = f"spot {pos} VWAP {vwap:,.2f}"
        if orb_hi and orb_lo:
            inside = orb_lo <= spot <= orb_hi
            note += f" · {'inside' if inside else 'outside'} ORB [{orb_lo:,.0f}–{orb_hi:,.0f}]"
        add("VWAP/ORB", "pass" if vwap else "warn", note)
    else:
        add("VWAP/ORB", "warn", "no VWAP available")

    # ── 8. OPTIONS FILTER ──
    pcr = signal.get("pcr") or signal.get("weekly_pcr")
    csignal = signal.get("contrarian_signal", "")
    iv = signal.get("atm_iv")
    notes = []
    if pcr is not None:
        notes.append(f"PCR {pcr}")
        if pcr < 0.7:
            notes.append("euphoric (fade calls)")
        elif pcr > 1.4:
            notes.append("panic (fade puts)")
    if iv is not None:
        notes.append(f"ATM IV {iv:.1f}")
    if notes:
        add("OPTIONS FILTER", "pass", " · ".join(notes))
    else:
        add("OPTIONS FILTER", "warn", "no PCR/IV — chain not loaded (token?)")

    # ── 9. LIQUIDITY CHECK ──
    call_lq = scalper.get("call") if isinstance(scalper.get("call"), dict) else {}
    oi = call_lq.get("oi")
    spct = call_lq.get("spread_pct")
    if oi is not None and spct is not None:
        oi_ok = oi >= 500
        sp_ok = spct <= 1.5
        if oi_ok and sp_ok:
            add("LIQUIDITY CHECK", "pass", f"OI {oi:,.0f} lots · spread {spct:.1f}% — liquid")
        else:
            issues = []
            if not oi_ok:
                issues.append(f"OI {oi:,.0f} < 500 lots")
            if not sp_ok:
                issues.append(f"spread {spct:.1f}% > 1.5%")
            add("LIQUIDITY CHECK", "warn", "thin — " + " · ".join(issues))
    else:
        add("LIQUIDITY CHECK", "warn", "no OI/spread from chain — verify manually")

    # ── 10. EXPECTED VALUE ──
    ev = signal.get("expected_move_1sd")
    tgt = None
    call = scalper.get("call") or {}
    if isinstance(call, dict):
        tgt = call.get("target")
    if ev and tgt:
        ev_ok = abs(tgt - spot) <= ev * 1.5
        add("EXPECTED VALUE", "pass" if ev_ok else "warn",
            f"1σ move {ev:,.0f} vs target {tgt:,.0f} — {'inside' if ev_ok else 'beyond'} 1.5σ")
    else:
        add("EXPECTED VALUE", "warn", "no 1σ/target to compare")

    # ── 11. RISK CHECK ──
    stop = call.get("stop") if isinstance(call, dict) else None
    if tgt and stop:
        risk = abs(spot - stop)
        reward = abs(tgt - spot)
        rr = (reward / risk) if risk > 0 else 0
        add("RISK CHECK", "pass" if rr >= 2 else "warn",
            f"R:R {rr:.1f} (stop {stop:,.0f} / target {tgt:,.0f})")
    else:
        add("RISK CHECK", "warn", "no explicit stop/target — size for 1×ATR stop, 2:1")

    # ── 11b. RISK LIMITS (day-level) ──
    rl = risk_check_limits(trades or [])
    if not rl["ok"]:
        labels = {"max_loss_day": "max ₹ loss/day hit",
                  "max_trades_day": "max trades/day reached",
                  "consecutive_losses": "consecutive-loss stop"}
        add("RISK LIMITS", "fail", " · ".join(labels.get(b, b) for b in rl["blocks"]))
    else:
        d = rl["details"]
        add("RISK LIMITS", "pass",
            f"net ₹{d['net_rs']:,.0f} · {d['trades']} trades · {d['consecutive_losses']} consec losses")

    # ── 12. EXECUTION COST ──
    lot = {"nifty": 65, "bnf": 15}.get(scalper.get("asset") or signal.get("asset") or "nifty", 0)
    entry_prem = call.get("entry") if isinstance(call, dict) else None
    if entry_prem and lot:
        pct = cost_pct(entry_prem, entry_prem, lot)
        amt = round_trip_cost(entry_prem, entry_prem, lot)
        add("EXECUTION COST", "pass" if pct < 1.0 else "warn",
            f"~{pct:.2f}% round-trip (₹{amt:.0f}) — {'ok' if pct < 1.0 else 'thin edge on cheap premium'}")
    else:
        add("EXECUTION COST", "warn", "factor ~0.1–0.3% round-trip (brokerage + slippage)")

    # ── VERDICT ──
    hard_fail = [s for s in steps if s["status"] == "fail"]
    if hard_fail:
        verdict = "NO TRADE"
        reason = " · ".join(f"{s['step']}: {s['detail']}" for s in hard_fail)
        confidence = "high" if any(s["step"] in ("MARKET DATA", "TIME OF DAY") for s in hard_fail) else "moderate"
    else:
        verdict = "TRADE"
        warns = [s["step"] for s in steps if s["status"] == "warn"]
        reason = ("All hard gates pass" +
                  (f" · review: {', '.join(warns)}" if warns else ""))
        confidence = "moderate" if warns else "high"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "reason": reason,
        "steps": steps,
        "hard_fails": [s["step"] for s in hard_fail],
        "direction": regime.get("direction", "flat"),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(trade_gate(), indent=2, default=str))
