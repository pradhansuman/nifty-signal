"""Offline tests: risk engine (day limits + position sizing)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import risk_engine as re_


class RiskEngineTest(unittest.TestCase):
    def test_all_clear_no_trades(self):
        r = re_.check_limits([])
        self.assertTrue(r["ok"])
        self.assertEqual(r["details"]["trades"], 0)

    def test_max_loss_day(self):
        trades = [{"pnl_rs": -6000.0}, {"pnl_rs": -5000.0}]
        r = re_.check_limits(trades)  # default max_loss 10,000
        self.assertFalse(r["ok"])
        self.assertIn("max_loss_day", r["blocks"])

    def test_max_trades_day(self):
        trades = [{"pnl_rs": 100.0}] * 10  # default max_trades 10
        r = re_.check_limits(trades)
        self.assertIn("max_trades_day", r["blocks"])

    def test_consecutive_losses(self):
        trades = [{"pnl_rs": -1000.0}, {"pnl_rs": -2000.0}, {"pnl_rs": -3000.0}]
        r = re_.check_limits(trades)  # default 3 consecutive
        self.assertIn("consecutive_losses", r["blocks"])
        self.assertEqual(r["details"]["consecutive_losses"], 3)

    def test_consecutive_resets_on_win(self):
        trades = [{"pnl_rs": -1000.0}, {"pnl_rs": -2000.0}, {"pnl_rs": 500.0}, {"pnl_rs": -300.0}]
        r = re_.check_limits(trades)
        self.assertEqual(r["details"]["consecutive_losses"], 1)

    def test_position_size(self):
        # ₹1,00,000 capital, 1% risk = ₹1,000 budget; stop 12 → ~83 units → 1 lot (65)
        p = re_.position_size(100000, 1.0, 12.0, 65)
        self.assertEqual(p["budget_rs"], 1000.0)
        self.assertEqual(p["lots"], 1)

    def test_position_size_zero_stop(self):
        p = re_.position_size(100000, 1.0, 0.0, 65)
        self.assertEqual(p["lots"], 0)


if __name__ == "__main__":
    unittest.main()
