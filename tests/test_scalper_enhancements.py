"""Unit tests for scalper_enhancements.py — the 5 candidate confirmation filters.

All are OFF by default in the live/backtest path; these tests verify each
predicate's truth table and the additive indicator attachments.
"""
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scalper_enhancements as enh


def _P(series_dict):
    """Build a precompute-like dict of float Series from {key: list}."""
    return {k: pd.Series(v, dtype=float) for k, v in series_dict.items()}


class IndicatorTest(unittest.TestCase):
    def test_atr_positive_volatile_zero_flat(self):
        highs = pd.Series([100, 102, 101, 103], dtype=float)
        lows = pd.Series([99, 100, 99, 101], dtype=float)
        closes = pd.Series([100, 101, 100, 102], dtype=float)
        a = enh.atr(highs, lows, closes, n=2)
        self.assertTrue((a.dropna() > 0).all())

        flat = pd.Series([100.0] * 8)
        a0 = enh.atr(flat, flat, flat, n=2)
        self.assertTrue((a0.dropna() == 0).all())

    def test_adx_range_and_trend_gt_chop(self):
        n = 80
        idx = pd.RangeIndex(n)
        t = pd.Series(np.linspace(100, 180, n), index=idx)
        adx_trend = enh.adx(t + 1, t - 1, t, n=14)
        self.assertTrue((adx_trend.dropna() >= 0).all())
        self.assertTrue((adx_trend.dropna() <= 100).all())

        c = pd.Series(100 + 3 * np.sin(np.arange(n) / 2.0), index=idx)
        adx_chop = enh.adx(c + 1, c - 1, c, n=14)
        self.assertGreater(adx_trend.dropna().iloc[-1], adx_chop.dropna().iloc[-1])

    def test_attach_indicators_additive(self):
        P = _P({"highs": [102, 103], "lows": [99, 100], "closes": [100, 101],
                "vwap": [100.0, 100.5]})
        orig_keys = set(P.keys())
        enh.attach_indicators(P)
        self.assertTrue({"atr", "adx", "adx_slope", "vwap_slope"} <= set(P.keys()))
        self.assertTrue(orig_keys <= set(P.keys()))  # nothing removed


class VwapSlopeTest(unittest.TestCase):
    def test_long_confirm(self):
        P = _P({"vwap": [100, 100, 101, 102, 103, 104],
                "closes": [101, 101, 102, 103, 104, 105]})
        self.assertTrue(enh.vwap_slope_ok(P, 5, 1, window=5))

    def test_short_confirm(self):
        P = _P({"vwap": [104, 103, 102, 101, 100, 99],
                "closes": [103, 102, 101, 100, 99, 98]})
        self.assertTrue(enh.vwap_slope_ok(P, 5, -1, window=5))

    def test_price_side_disagrees(self):
        # price above VWAP but VWAP falling → LONG blocked
        P = _P({"vwap": [104, 103, 102, 101, 100, 99],
                "closes": [105, 105, 105, 105, 105, 105]})
        self.assertFalse(enh.vwap_slope_ok(P, 5, 1, window=5))

    def test_insufficient_history_none(self):
        P = _P({"vwap": [100, 101, 102], "closes": [100, 101, 102]})
        self.assertIsNone(enh.vwap_slope_ok(P, 2, 1, window=5))


class EmaSepAtrTest(unittest.TestCase):
    def test_meaningful_separation_long(self):
        P = _P({"ema9": [100, 101, 102], "ema21": [99, 99, 99], "atr": [1, 1, 1]})
        self.assertTrue(enh.ema_sep_atr_ok(P, 2, 1, min_sep=0.5))

    def test_short_requires_negative_sep(self):
        P = _P({"ema9": [100, 101, 102], "ema21": [99, 99, 99], "atr": [1, 1, 1]})
        # sep = +3, but SHORT needs sep <= -0.5 → blocked
        self.assertFalse(enh.ema_sep_atr_ok(P, 2, -1, min_sep=0.5))

    def test_tiny_sep_is_noise(self):
        P = _P({"ema9": [99, 99, 99.1], "ema21": [99, 99, 99], "atr": [1, 1, 1]})
        self.assertFalse(enh.ema_sep_atr_ok(P, 2, 1, min_sep=0.5))

    def test_zero_atr_none(self):
        P = _P({"ema9": [100], "ema21": [99], "atr": [0]})
        self.assertIsNone(enh.ema_sep_atr_ok(P, 0, 1))


class AdxDirTest(unittest.TestCase):
    def test_above_level_and_rising(self):
        P = _P({"adx": [20, 24, 28], "adx_slope": [0, 4, 4]})
        self.assertTrue(enh.adx_dir_ok(P, 2, 1, level=25))

    def test_below_level_blocked(self):
        P = _P({"adx": [20, 20, 20], "adx_slope": [0, 1, 1]})
        self.assertFalse(enh.adx_dir_ok(P, 2, 1, level=25))

    def test_falling_blocked(self):
        P = _P({"adx": [30, 30, 30], "adx_slope": [0, -1, -1]})
        self.assertFalse(enh.adx_dir_ok(P, 2, 1, level=25))

    def test_nan_none(self):
        P = _P({"adx": [np.nan], "adx_slope": [np.nan]})
        self.assertIsNone(enh.adx_dir_ok(P, 0, 1))


class OrbRetestTest(unittest.TestCase):
    def test_long_breakout_retest_continuation(self):
        P = _P({
            "orb_high": [100] * 5, "orb_low": [90] * 5,
            "highs": [95, 101, 100, 100, 102],
            "lows": [93, 99, 99.5, 100, 100.5],
            "closes": [96, 100, 100, 101, 102],
        })
        self.assertTrue(enh.orb_retest_ok(P, 4, 1, tol=0.003, lookback=15))

    def test_no_breakout_blocked(self):
        P = _P({
            "orb_high": [100] * 5, "orb_low": [90] * 5,
            "highs": [95, 96, 97, 98, 99],
            "lows": [93, 94, 95, 96, 97],
            "closes": [96, 97, 98, 99, 99],
        })
        self.assertFalse(enh.orb_retest_ok(P, 4, 1, tol=0.003, lookback=15))

    def test_short_breakdown_retest_continuation(self):
        P = _P({
            "orb_high": [100] * 5, "orb_low": [90] * 5,
            "highs": [95, 92, 91, 90.5, 90],
            "lows": [88, 89, 90, 90, 88],
            "closes": [92, 90, 90, 89, 88],
        })
        self.assertTrue(enh.orb_retest_ok(P, 4, -1, tol=0.003, lookback=15))


class MicrostructureTest(unittest.TestCase):
    def _ce(self, bid=99.5, ask=100.5, ltp=100.0, oi=1000, vol=10000):
        return {"ce_bid": bid, "ce_ask": ask, "ce_ltp": ltp,
                "ce_oi": oi, "ce_vol": vol, "ce_delta": 0.55}

    def test_good_quote_passes(self):
        self.assertTrue(enh.microstructure_ok(self._ce(), 1))

    def test_wide_spread_blocks(self):
        self.assertFalse(enh.microstructure_ok(self._ce(bid=98.0, ask=102.0), 1))

    def test_low_oi_blocks(self):
        self.assertFalse(enh.microstructure_ok(self._ce(oi=100), 1))

    def test_low_volume_blocks(self):
        self.assertFalse(enh.microstructure_ok(self._ce(vol=100), 1))

    def test_missing_quote_blocks(self):
        self.assertFalse(enh.microstructure_ok({"ce_ltp": None}, 1))

    def test_pe_side_uses_pe_fields(self):
        row = {"pe_bid": 99.5, "pe_ask": 100.5, "pe_ltp": 100.0,
               "pe_oi": 1000, "pe_vol": 10000, "pe_delta": -0.55}
        self.assertTrue(enh.microstructure_ok(row, -1))


if __name__ == "__main__":
    unittest.main()
