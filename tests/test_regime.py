"""Offline tests: session regime classifier."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import regime


class RegimeTest(unittest.TestCase):
    def test_trending_bullish(self):
        r = regime.session_regime(35, 30, 15, 15, 24500, 24300)
        self.assertEqual(r["regime"], "TRENDING")
        self.assertEqual(r["direction"], "bullish")
        self.assertIn("momentum", r["strategy"].lower())

    def test_trending_bearish(self):
        r = regime.session_regime(28, 12, 28, 16, 24000, 24400)
        self.assertEqual(r["regime"], "TRENDING")
        self.assertEqual(r["direction"], "bearish")

    def test_choppy(self):
        r = regime.session_regime(14, 20, 19, 11, 24300, 24350)
        self.assertEqual(r["regime"], "CHOPPY")

    def test_range_at_200ema(self):
        # ADX weak + spot pinned near 200 EMA + vwap present → RANGE
        r = regime.session_regime(16, 20, 19, 11, 24350, 24348, vwap=24349)
        self.assertEqual(r["regime"], "RANGE")

    def test_transition(self):
        r = regime.session_regime(22, 23, 18, 13, 24300, 24350)
        self.assertEqual(r["regime"], "TRANSITION")

    def test_none_inputs_do_not_crash(self):
        r = regime.session_regime(None, None, None, None, None, None, vwap=None)
        self.assertIn(r["regime"], ("TRENDING", "TRANSITION", "CHOPPY", "RANGE"))


if __name__ == "__main__":
    unittest.main()
