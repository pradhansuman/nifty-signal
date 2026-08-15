"""Offline tests for the stock-movers backtest helpers (synthetic data)."""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".openclaw", "tmp"))

import stock_movers_backtest as sb


class MoversBacktestTest(unittest.TestCase):

    def test_stats_empty(self):
        s = sb._stats([])
        self.assertEqual(s["trades"], 0)

    def test_stats_win_rate_and_pf(self):
        s = sb._stats([2.0, 1.0, -1.0])
        self.assertEqual(s["trades"], 3)
        self.assertEqual(s["win_rate"], 66.7)
        self.assertGreater(s["profit_factor"], 1)

    def test_signals_extracts_rows(self):
        n = 80
        idx = pd.date_range("2026-01-01", periods=n, freq="B")
        closes = [100 * (1.01 ** i) for i in range(n)]  # steady uptrend
        df = pd.DataFrame({
            "Open": [c * 0.995 for c in closes], "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes], "Close": closes,
            "Volume": [1_000_000] * n,
        }, index=idx)
        df.columns = pd.MultiIndex.from_product([["STK.NS"], df.columns])
        sig = sb._signals(df)
        self.assertGreater(len(sig), 0)
        self.assertIn("trend", sig.columns)
        self.assertIn("day_pct", sig.columns)


if __name__ == "__main__":
    unittest.main()
