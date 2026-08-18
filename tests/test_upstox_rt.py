"""Offline tests: Upstox real-time candle feed (aggregation + resample)."""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import upstox_rt as urt


class UpstoxRtTest(unittest.TestCase):
    def setUp(self):
        urt._candles = {a: [] for a in urt.SYMBOLS}
        urt._last_ltp = {a: None for a in urt.SYMBOLS}

    def test_tick_populates_candles_and_ltp(self):
        orig = urt._fetch_ltp
        urt._fetch_ltp = lambda: {"nifty": 24100.0, "bnf": 57000.0, "sensex": 77000.0}
        try:
            urt._tick()
            self.assertEqual(urt.last_price("nifty"), 24100.0)
            with urt._lock:
                self.assertEqual(len(urt._candles["nifty"]), 1)
            # candle shape: [ts, open, high, low, close]
            c = urt._candles["nifty"][0]
            self.assertEqual(c[1], 24100.0)  # open
            self.assertEqual(c[2], 24100.0)  # high
            self.assertEqual(c[4], 24100.0)  # close
        finally:
            urt._fetch_ltp = orig

    def test_get_bars_columns_and_resample(self):
        # inject 30 synthetic 1m candles
        import datetime as dt
        base = dt.datetime(2026, 8, 18, 9, 15)
        bars = []
        for i in range(30):
            ts = (base + dt.timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M")
            px = 24000 + i
            bars.append([ts, px, px + 2, px - 2, px + 1])
        with urt._lock:
            urt._candles["nifty"] = bars

        df = urt.get_bars("nifty")
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 30)
        for col in ("Open", "High", "Low", "Close", "Volume"):
            self.assertIn(col, df.columns)

        df5 = urt.get_bars("nifty", rule="5min")
        self.assertIsNotNone(df5)
        self.assertLess(len(df5), len(df))

    def test_get_bars_empty(self):
        df = urt.get_bars("nifty")
        self.assertIsNone(df)

    def test_get_bars_unknown_asset(self):
        self.assertIsNone(urt.get_bars("foo"))


if __name__ == "__main__":
    unittest.main()
