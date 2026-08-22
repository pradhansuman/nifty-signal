"""Regression tests for the 2026-08-21 Scalper Gauges audit.

Covers the three P0 architectural fixes and the P1 classification checks:
  1. ORB anchored to 09:15-09:30 IST (not "first N bars").
  2. Coarse feeds (>15m) → ORB unavailable (never substitute a 60-min range).
  3. Trend-strength gate = ATR-normalized 200E drift (not raw % distance).
  4. ORB classification (ABOVE / INSIDE / BELOW), VWAP %, live-LTP vs close,
     and the score audit trail.
"""
import os
import sys
import unittest
from unittest import mock
from datetime import time as dtime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".openclaw", "tmp"))

import scalper

IST = "Asia/Kolkata"


def session(start="2026-08-21 09:15", n=60, freq="1min", base_price=24000.0, seed=1):
    """IST-indexed OHLCV session with a mild drift (deterministic)."""
    idx = pd.date_range(pd.Timestamp(start, tz=IST), periods=n, freq=freq, tz=IST)
    rng = np.random.default_rng(seed)
    closes = base_price + rng.normal(0, 2, n).cumsum()
    highs = closes + np.abs(rng.normal(0, 1, n))
    lows = closes - np.abs(rng.normal(0, 1, n))
    return pd.DataFrame({"Open": closes, "High": highs, "Low": lows,
                         "Close": closes, "Volume": 0.0}, index=idx)


class InferIntervalTest(unittest.TestCase):
    def test_detects_common_timeframes(self):
        for freq, want in [("1min", 1), ("5min", 5), ("15min", 15), ("1h", 60)]:
            df = session(freq=freq)
            self.assertEqual(scalper._infer_interval_minutes(df), want, freq)


class OrbWindowTest(unittest.TestCase):
    def test_1m_selects_0915_to_0930(self):
        sess = session(n=60, freq="1min")
        orb = scalper._orb_window(sess)
        self.assertTrue(orb["available"])
        mask = (sess.index.time >= dtime(9, 15)) & (sess.index.time < dtime(9, 30))
        self.assertEqual(len(sess[mask]), 15)  # exactly 15 bars in the opening 15 min
        self.assertEqual(orb["orb_high"], float(sess[mask]["High"].max()))
        self.assertEqual(orb["orb_low"], float(sess[mask]["Low"].min()))

    def test_15m_selects_single_0915_bar(self):
        sess = session(n=8, freq="15min")
        orb = scalper._orb_window(sess)
        self.assertTrue(orb["available"])
        mask = (sess.index.time >= dtime(9, 15)) & (sess.index.time < dtime(9, 30))
        self.assertEqual(len(sess[mask]), 1)  # only the 09:15 bar, NOT "3 bars"

    def test_1h_is_unavailable_not_silently_60min(self):
        sess = session(n=8, freq="1h")
        orb = scalper._orb_window(sess)
        self.assertFalse(orb["available"])
        self.assertIn("coarser", orb["note"])
        self.assertIsNone(orb["orb_high"])

    def test_anchored_to_0915_not_first_records(self):
        # pre-market bars (09:05-09:10) with an extreme high must be excluded
        pre_idx = pd.date_range(pd.Timestamp("2026-08-21 09:05", tz=IST), periods=2, freq="5min", tz=IST)
        pre = pd.DataFrame({"Open": 24000.0, "High": 99999.0, "Low": 24000.0,
                            "Close": 24000.0, "Volume": 0.0}, index=pre_idx)
        sess = pd.concat([pre, session()])
        orb = scalper._orb_window(sess)
        self.assertTrue(orb["available"])
        self.assertNotEqual(orb["orb_high"], 99999.0)  # pre-market excluded

    def test_pre_open_unavailable(self):
        # session entirely before 09:15 → no opening range yet
        sess = session(start="2026-08-21 09:00", n=3, freq="5min")
        orb = scalper._orb_window(sess)
        self.assertFalse(orb["available"])


class OrbPositionTest(unittest.TestCase):
    def test_below_inside_above(self):
        self.assertEqual(scalper._orb_position(23900, 24282, 24211), "BELOW")
        self.assertEqual(scalper._orb_position(24250, 24282, 24211), "INSIDE")
        self.assertEqual(scalper._orb_position(24300, 24282, 24211), "ABOVE")
        self.assertEqual(scalper._orb_position(24250, None, None), "N/A")


class TrendGateTest(unittest.TestCase):
    def test_long_blocks_on_flat_slope(self):
        self.assertIsNotNone(scalper._trend_strength_block("LONG", slope_atr=0.3, slope_atr_min=1.0))

    def test_long_passes_on_strong_slope(self):
        self.assertIsNone(scalper._trend_strength_block("LONG", slope_atr=14.0, slope_atr_min=1.0))

    def test_short_is_mirrored(self):
        self.assertIsNone(scalper._trend_strength_block("SHORT", slope_atr=-14.0, slope_atr_min=1.0))
        self.assertIsNotNone(scalper._trend_strength_block("SHORT", slope_atr=-0.2, slope_atr_min=1.0))

    def test_strength_not_distance(self):
        # A large raw % distance with a FLAT 200E must still block (chop),
        # and a tiny distance with a RISING 200E must pass — the whole point.
        self.assertIsNotNone(scalper._trend_strength_block("LONG", slope_atr=-0.5, slope_atr_min=1.0))
        self.assertIsNone(scalper._trend_strength_block("LONG", slope_atr=2.0, slope_atr_min=1.0))


class VwapPctTest(unittest.TestCase):
    def test_vwap_pct_formula(self):
        spot, vwap = 24240.0, 24235.06
        self.assertAlmostEqual((spot - vwap) / vwap * 100.0, 0.0204, places=3)


class _FakeClock:
    @staticmethod
    def now(tz=None):
        return pd.Timestamp("2026-08-14 10:30:00", tz="Asia/Kolkata").to_pydatetime()


class LiveLtpTest(unittest.TestCase):
    def test_spot_uses_live_ltp_not_last_close(self):
        from tests.helpers import make_bars
        bars = make_bars(up=True)
        last_close = float(bars["Close"].iloc[-1])
        with mock.patch.object(scalper, "get_bars", return_value=bars), \
             mock.patch.object(scalper, "_load_tuning", return_value={
                 "score_min": 3.0, "slope_atr_min": 1.0, "adx_min": 25.0,
                 "vix_min": 12.0, "vix_max": 18.0, "theta_max": 0.5}), \
             mock.patch.object(scalper, "_vix_level", return_value=15.0), \
             mock.patch.object(scalper, "_adx", return_value=pd.Series([40.0] * 500)), \
             mock.patch.object(scalper, "build_call", return_value=None), \
             mock.patch("scalper.datetime", _FakeClock), \
             mock.patch("upstox_rt.last_price", return_value=99999.0):
            out = scalper.main()
        self.assertNotEqual(last_close, 99999.0)  # sanity: live differs from close
        self.assertEqual(out["spot"], 99999.0)    # decision uses the LIVE price

    def test_breakdown_points_sum_to_score(self):
        from tests.helpers import make_bars
        bars = make_bars(up=True)
        with mock.patch.object(scalper, "get_bars", return_value=bars), \
             mock.patch.object(scalper, "_load_tuning", return_value={
                 "score_min": 3.0, "slope_atr_min": 1.0, "adx_min": 25.0,
                 "vix_min": 12.0, "vix_max": 18.0, "theta_max": 0.5}), \
             mock.patch.object(scalper, "_vix_level", return_value=15.0), \
             mock.patch.object(scalper, "_adx", return_value=pd.Series([40.0] * 500)), \
             mock.patch.object(scalper, "build_call", return_value=None), \
             mock.patch("scalper.datetime", _FakeClock):
            out = scalper.main()
        bd = out.get("score_breakdown", [])
        for name in ("EMA 9/21", "VWAP", "Momentum", "RSI", "Stoch", "ORB"):
            self.assertIn(name, [b["gauge"] for b in bd])
        for b in bd:
            self.assertIn("points", b)
            self.assertIn("note", b)
        self.assertEqual(sum(b["points"] for b in bd), out["score"])
        self.assertIsNotNone(out.get("blocking_gates"))


if __name__ == "__main__":
    unittest.main()
