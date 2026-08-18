#!/usr/bin/env python3
"""
Session Regime — classifies today's market as TRENDING / TRANSITION / CHOPPY-RANGE
and maps it to the RIGHT scalping strategy (for a pure option BUYER).

Why this matters: an option buyer bleeds in chop. Picking the correct strategy for
the session type is worth more than adding more signals.

Pure function — no network, fully testable offline.
"""
from __future__ import annotations


def session_regime(adx, di_plus, di_minus, vix, spot, ema_200, vwap=None):
    """
    Returns dict:
      regime:      "TRENDING" | "TRANSITION" | "CHOPPY" | "RANGE"
      direction:   "bullish" | "bearish" | "flat"
      label:       human label
      strategy:    recommended scalping approach (buyer-only)
      confidence:  "high" | "moderate" | "low"
      reason:      why
      adx/di_spread/vix/spot/ema_200/trend_dist_pct  (echoed inputs)
    """
    try:
        adx = float(adx)
    except (TypeError, ValueError):
        adx = 0.0
    try:
        di_plus = float(di_plus)
        di_minus = float(di_minus)
    except (TypeError, ValueError):
        di_plus = di_minus = 0.0
    try:
        vix = float(vix)
    except (TypeError, ValueError):
        vix = 0.0
    try:
        spot = float(spot)
        ema_200 = float(ema_200)
    except (TypeError, ValueError):
        spot = ema_200 = 0.0
    try:
        vwap = float(vwap) if vwap is not None else None
    except (TypeError, ValueError):
        vwap = None

    di_spread = di_plus - di_minus
    if di_spread > 5:
        direction = "bullish"
    elif di_spread < -5:
        direction = "bearish"
    else:
        direction = "flat"

    trend_dist_pct = ((spot - ema_200) / ema_200 * 100.0) if ema_200 else 0.0

    # ── Core classification ──
    if adx >= 25:
        regime = "TRENDING"
        confidence = "high" if adx >= 30 else "moderate"
        label = ("Bullish Trend" if direction == "bullish" else
                 "Bearish Trend" if direction == "bearish" else "Trending (flat bias)")
        strategy = ("Ride momentum — scalper Buy CE + ORB breakout + 9/21 cross "
                    "in the trend direction. Hold winners, trail stop.")
    elif adx >= 20:
        regime = "TRANSITION"
        confidence = "moderate"
        label = "Transition (trend building/fading)"
        strategy = ("Don't force it. Wait for confirmation — 20 EMA reclaim or "
                    "200 EMA bounce only. Half size, quick exit.")
    else:
        regime = "CHOPPY"
        confidence = "high" if adx < 15 else "moderate"
        label = "Choppy / No Trend"
        strategy = ("Option buyers stand aside or VWAP-reversion only. "
                    "Chop is where premium dies — small size or no trade.")

    # ── Refine CHOPPY into RANGE when pinned near the 200 EMA ──
    if regime == "CHOPPY" and abs(trend_dist_pct) <= 0.5 and vwap is not None:
        regime = "RANGE"
        label = "Range (pinned at 200 EMA)"
        strategy = ("Range-bound at the 200 EMA — fade the extremes only, or wait "
                    "for a clean breakout/reclaim. No mid-range entries.")

    # ── VWAP confirmation for trending days ──
    if regime == "TRENDING" and vwap is not None:
        above = spot >= vwap
        aligned = (direction == "bullish" and above) or (direction == "bearish" and not above)
        if not aligned:
            confidence = "moderate"
            label += " (VWAP-divergent)"
            strategy += " NOTE: price vs VWAP disagrees — tighten risk."

    reason = (f"ADX {adx:.1f} ({'strong' if adx >= 30 else 'mild' if adx >= 20 else 'weak'}), "
              f"DI+ {di_plus:.0f} vs DI- {di_minus:.0f} ({direction}), "
              f"VIX {vix:.1f}, spot {trend_dist_pct:+.2f}% vs 200 EMA")

    return {
        "regime": regime,
        "direction": direction,
        "label": label,
        "strategy": strategy,
        "confidence": confidence,
        "reason": reason,
        "adx": round(adx, 1),
        "di_spread": round(di_spread, 1),
        "vix": round(vix, 1),
        "spot": round(spot, 2),
        "ema_200": round(ema_200, 2),
        "trend_dist_pct": round(trend_dist_pct, 2),
    }


if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, ".")
    # Pull live signal + VWAP if possible, else demo values
    try:
        import nifty_monitor as nm
        s = nm.get_signal()
        r = session_regime(s.get("adx"), s.get("di_plus"), s.get("di_minus"),
                           s.get("vix"), s.get("spot"), s.get("ema_200"))
    except Exception:
        r = session_regime(18.1, 29.0, 20.1, 11.32, 24239.7, 24441.67)
    print(json.dumps(r, indent=2, default=str))
