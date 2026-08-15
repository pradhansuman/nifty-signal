"""Offline tests for stock_movers screening (synthetic DataFrame, no network)."""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".openclaw", "tmp"))

import stock_movers as sm


def _frame(closes, name="TICKER"):
    """Build a daily OHLCV frame (MultiIndex cols) from a close series."""
    idx = pd.date_range("2026-05-01", periods=len(closes), freq="B")
    n = len(closes)
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    vols = [1_000_000 + i * 1000 for i in range(n)]
    df = pd.DataFrame({
        "Open": closes, "High": highs, "Low": lows, "Close": closes, "Volume": vols,
    }, index=idx)
    df.columns = pd.MultiIndex.from_product([[name], df.columns])
    return df


class StockMoversScreenTest(unittest.TestCase):

    def test_uptrend_stock_appears_in_swing(self):
        # steady uptrend: closes rise ~1%/day, last 6 sessions +8%
        closes = [100 * (1.01 ** i) for i in range(60)]
        df = _frame(closes)
        d = sm.main(df)
        swing = d["swing"]
        self.assertTrue(any(r["name"] == "TICKER" and r["direction"] == "UP" for r in swing))
        r = next(r for r in swing if r["name"] == "TICKER")
        self.assertGreater(r["target"], r["price"])
        self.assertGreater(r["target_pct"], 0)
        self.assertEqual(r["timeline"], "5–10 sessions")

    def test_big_day_mover_appears_in_day(self):
        # flat base, then a +3% spike on above-average volume
        closes = [100] * 30 + [103]
        df = _frame(closes)
        df.loc[df.index[-1], ("TICKER", "Volume")] = 5_000_000  # volume spike
        d = sm.main(df)
        day = d["day_trade"]
        self.assertTrue(any(r["name"] == "TICKER" and r["direction"] == "UP" for r in day))
        r = next(r for r in day if r["name"] == "TICKER")
        self.assertGreater(r["target"], r["price"])
        self.assertEqual(r["timeline"], "today (intraday)")

    def test_flat_stock_excluded(self):
        closes = [100] * 60  # no move at all
        df = _frame(closes)
        d = sm.main(df)
        self.assertEqual(d["day_trade"], [])
        self.assertEqual(d["swing"], [])

    def test_down_mover_direction(self):
        closes = [100] * 30 + [96]  # −4% day
        df = _frame(closes)
        df.loc[df.index[-1], ("TICKER", "Volume")] = 4_000_000
        d = sm.main(df)
        day = d["day_trade"]
        self.assertTrue(any(r["direction"] == "DOWN" for r in day))
        r = next(r for r in day if r["direction"] == "DOWN")
        self.assertLess(r["target"], r["price"])
        self.assertLess(r["target_pct"], 0)

    def test_rows_are_clean(self):
        closes = [100 * (1.005 ** i) for i in range(60)]
        df = _frame(closes)
        df.loc[df.index[-1], ("TICKER", "Volume")] = 3_000_000
        d = sm.main(df)
        for r in d["day_trade"] + d["swing"]:
            self.assertEqual(r["price"], r["price"])  # not NaN
            self.assertEqual(r["target"], r["target"])
            self.assertTrue(r["symbol"])


if __name__ == "__main__":
    unittest.main()
