"""Offline tests: trade gate decision chain."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trade_gate


def _base():
    return dict(
        signal={"spot": 24400, "ema_200": 24300, "distance_pct": 0.4,
                "expected_move_1sd": 80, "contrarian_signal": "NEUTRAL",
                "weekly_pcr": 1.0, "atm_iv": 14.5, "signal": "BUY_CALLS"},
        regime={"regime": "TRENDING", "direction": "bullish", "label": "Bullish Trend"},
        scalper={"spot": 24400, "score": 4, "score_min": 3.0, "window": "OPEN",
                 "bias": "LONG", "vwap": 24350, "orb_high": 24450, "orb_low": 24250,
                 "call": {"stop": 24320, "target": 24560}},
        intraday={"vwap": {"vwap": 24350}},
    )


class TradeGateTest(unittest.TestCase):
    def test_all_pass_trending(self):
        g = trade_gate.trade_gate(**_base())
        self.assertEqual(g["verdict"], "TRADE")

    def test_no_trade_choppy(self):
        b = _base()
        b["regime"]["regime"] = "CHOPPY"
        b["regime"]["label"] = "Choppy / No Trend"
        b["scalper"]["score"] = 1
        g = trade_gate.trade_gate(**b)
        self.assertEqual(g["verdict"], "NO TRADE")
        fails = g["hard_fails"]
        self.assertIn("MARKET REGIME", fails)

    def test_no_trade_window_blocked(self):
        b = _base()
        b["scalper"]["window"] = "BLOCKED"
        b["scalper"]["window_reason"] = "lunch chop"
        g = trade_gate.trade_gate(**b)
        self.assertEqual(g["verdict"], "NO TRADE")

    def test_no_data_blocks(self):
        g = trade_gate.trade_gate()
        self.assertEqual(g["verdict"], "NO TRADE")
        self.assertIn("MARKET DATA", g["hard_fails"])

    def test_weak_momentum_blocks_in_trending(self):
        b = _base()
        b["scalper"]["score"] = 1
        g = trade_gate.trade_gate(**b)
        self.assertEqual(g["verdict"], "NO TRADE")
        self.assertIn("MOMENTUM/VOLUME", g["hard_fails"])

    def test_steps_length(self):
        g = trade_gate.trade_gate(**_base())
        # 12 pre-trade steps
        self.assertEqual(len(g["steps"]), 12)


if __name__ == "__main__":
    unittest.main()
