"""Offline tests: EMA crossover signal produces actionable entry/stop/target."""
import os
import sys
import unittest

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".openclaw", "tmp"))

import intraday_signals as isig


def _df_with_golden_cross(n=40):
    """Downtrend then sharp late rally so 9 EMA crosses above 21 EMA on the last bar."""
    idx = pd.date_range("2026-01-01 09:15", periods=n, freq="5min")
    closes = [1000 - i * 2 for i in range(n - 3)] + [950, 980, 1030]
    closes = [float(c) for c in closes]
    highs = [c + 5 for c in closes]
    lows = [c - 5 for c in closes]
    opens = [closes[0]] + closes[:-1]
    df = pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": closes,
                       "Volume": [1000000] * n}, index=idx)
    return df


class EmaCrossTest(unittest.TestCase):

    def test_golden_cross_is_actionable(self):
        r = isig.ema_signal(_df_with_golden_cross())
        self.assertEqual(r["signal"], "EMA_BUY")
        self.assertIn("entry", r)
        self.assertIsNotNone(r["entry"])
        self.assertLess(r["stop"], r["entry"])       # BUY stop below entry
        self.assertGreater(r["target"], r["entry"])  # BUY target above entry
        self.assertEqual(r["rr"], 2.0)
        self.assertIn("exit_rule", r)

    def test_death_cross_is_actionable(self):
        df = _df_with_golden_cross()
        # mirror (flip closes) → EMA9 crosses below EMA21
        closes = [2000 - c for c in df["Close"]]  # inverted trend
        df2 = df.copy()
        df2["Close"] = closes
        df2["High"] = [c + 5 for c in closes]
        df2["Low"] = [c - 5 for c in closes]
        r = isig.ema_signal(df2)
        self.assertEqual(r["signal"], "EMA_SELL")
        self.assertGreater(r["stop"], r["entry"])   # SELL stop above entry
        self.assertLess(r["target"], r["entry"])    # SELL target below entry


if __name__ == "__main__":
    unittest.main()


class TrendCrossTest(unittest.TestCase):
    def _h1_uptrend(self, n=80):
        idx = pd.date_range("2026-01-01", periods=n, freq="1h")
        closes = [1000 - i for i in range(n - 4)] + [960, 980, 1010, 1050]
        closes = [float(c) for c in closes]
        return pd.DataFrame({"Open": [closes[0]] + closes[:-1],
                             "High": [c + 5 for c in closes], "Low": [c - 5 for c in closes],
                             "Close": closes, "Volume": [1e6] * n}, index=idx)

    def test_golden_cross_20_50(self):
        r = isig.trend_cross_signal(self._h1_uptrend())
        self.assertEqual(r["signal"], "GOLDEN_CROSS")
        self.assertLess(r["stop"], r["entry"])
        self.assertGreater(r["target"], r["entry"])

    def test_ema20_reclaim(self):
        n = 40
        idx = pd.date_range("2026-01-01 09:15", periods=n, freq="15min")
        closes = [1000 - i for i in range(n - 1)] + [1030]  # downtrend then final spike
        closes = [float(c) for c in closes]
        df = pd.DataFrame({"Open": [closes[0]] + closes[:-1],
                           "High": [c + 5 for c in closes], "Low": [c - 5 for c in closes],
                           "Close": closes, "Volume": [1e6] * n}, index=idx)
        r = isig.ema20_reclaim_signal(df)
        self.assertEqual(r["signal"], "RECLAIM")
        self.assertLess(r["stop"], r["entry"])


class VwapZeroVolumeTest(unittest.TestCase):
    """Index LTP (Upstox) and NSE Yahoo indices have ZERO volume — VWAP must
    degrade to a typical-price running mean, never NaN (regression for the
    `(typical*vol).cumsum()/vol.cumsum()` 0/0 bug)."""

    def test_zero_volume_returns_finite_vwap(self):
        n = 30
        idx = pd.date_range("2026-01-01 09:15", periods=n, freq="5min")
        closes = [1000.0 + i for i in range(n)]
        df = pd.DataFrame({"Open": closes, "High": [c + 5 for c in closes],
                           "Low": [c - 5 for c in closes], "Close": closes,
                           "Volume": [0.0] * n}, index=idx)
        r = isig.vwap_signal(df)
        self.assertIsNotNone(r["vwap"])
        self.assertTrue(np.isfinite(r["vwap"]))
        self.assertGreater(r["vwap"], 0)

    def test_missing_volume_column_returns_finite_vwap(self):
        n = 30
        idx = pd.date_range("2026-01-01 09:15", periods=n, freq="5min")
        closes = [1000.0 + i for i in range(n)]
        df = pd.DataFrame({"Open": closes, "High": [c + 5 for c in closes],
                           "Low": [c - 5 for c in closes], "Close": closes}, index=idx)
        r = isig.vwap_signal(df)
        self.assertIsNotNone(r["vwap"])
        self.assertTrue(np.isfinite(r["vwap"]))

    def test_flat_zero_volume_is_neutral(self):
        n = 30
        idx = pd.date_range("2026-01-01 09:15", periods=n, freq="5min")
        closes = [1000.0] * n
        df = pd.DataFrame({"Open": closes, "High": [c + 5 for c in closes],
                           "Low": [c - 5 for c in closes], "Close": closes,
                           "Volume": [0.0] * n}, index=idx)
        r = isig.vwap_signal(df)
        self.assertEqual(r["signal"], "NEUTRAL")
