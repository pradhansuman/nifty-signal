"""Offline tests: MFE / MAE / R excursion computation."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nifty_server as ns


class ExcursionTest(unittest.TestCase):
    def test_options_long(self):
        # nifty CE: premium target above entry, stop below (risk = entry - stop)
        c = {"asset": "nifty", "signal": "SCALP_LONG", "entry": 100.0, "stop": 90.0,
             "target": 120.0, "highest": 120.0, "lowest": 95.0, "pnl_pts": 20.0}
        ns._scalp_excursion(c)
        self.assertEqual(c["mfe_r"], 2.0)    # 20/10
        self.assertEqual(c["mae_r"], 0.5)    # 5/10
        self.assertEqual(c["realized_r"], 2.0)

    def test_spot_short(self):
        # btc SHORT: favorable = price down; risk = stop - entry
        c = {"asset": "btc", "signal": "SCALP_SHORT", "entry": 100.0, "stop": 110.0,
             "target": 80.0, "highest": 105.0, "lowest": 90.0, "pnl_pts": 10.0}
        ns._scalp_excursion(c)
        self.assertEqual(c["mfe_r"], 1.0)    # (100-90)/10
        self.assertEqual(c["mae_r"], 0.5)    # (105-100)/10
        self.assertEqual(c["realized_r"], 1.0)

    def test_spot_long(self):
        c = {"asset": "sensex", "signal": "SCALP_LONG", "entry": 100.0, "stop": 95.0,
             "target": 110.0, "highest": 108.0, "lowest": 98.0, "pnl_pts": 8.0}
        ns._scalp_excursion(c)
        self.assertEqual(c["mfe_r"], 1.6)    # 8/5
        self.assertEqual(c["mae_r"], 0.4)    # 2/5
        self.assertEqual(c["realized_r"], 1.6)

    def test_missing_stop_returns_unchanged(self):
        c = {"asset": "nifty", "entry": 100.0, "highest": 105.0, "lowest": 95.0}
        before = set(c.keys())
        ns._scalp_excursion(c)
        self.assertEqual(set(c.keys()), before)  # no new fields added


if __name__ == "__main__":
    unittest.main()
