"""Offline tests: realistic round-trip cost model (Indian F&O option buyer)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cost_model as cm


class CostModelTest(unittest.TestCase):
    def test_round_trip_cost_nifty_120(self):
        # premium ₹120, lot 65 → ~₹64.35
        self.assertAlmostEqual(cm.round_trip_cost(120, 120, 65), 64.35, delta=0.05)

    def test_flat_brokerage_dominates_cheap_premium(self):
        # ₹60 premium lot: cost ≈ 55.77 → ~1.43% of lot value
        pct = cm.cost_pct(60, 60, 65)
        self.assertAlmostEqual(pct, 1.43, delta=0.05)

    def test_cost_pct_rich_premium(self):
        # ₹200 premium lot: ~0.58%
        self.assertAlmostEqual(cm.cost_pct(200, 200, 65), 0.58, delta=0.05)

    def test_cost_per_unit(self):
        # cost_per_unit = round_trip_cost / lot_size
        cu = cm.cost_per_unit(120, 120, 65)
        self.assertAlmostEqual(cu, 64.35 / 65, delta=0.01)

    def test_breakeven_move_includes_spread(self):
        # breakeven = 2*half_spread + cost_per_unit
        be = cm.breakeven_move(120, 120, 65, half_spread=1.5)
        self.assertAlmostEqual(be, 3.0 + 64.35 / 65, delta=0.05)

    def test_zero_lot_no_crash(self):
        self.assertEqual(cm.cost_pct(120, 120, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
