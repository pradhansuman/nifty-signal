"""Offline tests: scalper.optionize maps spot levels → option premium terms."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scalper


def _fake_chain():
    return {
        "expiry": "2026-08-25",
        "atm": 24200,
        "chain_spot": 24210.0,
        "rows": [
            {"strike": 24200, "ce_ltp": 156.0, "ce_delta": 0.57, "ce_ask": 156.3,
             "pe_ltp": 140.0, "pe_delta": -0.43, "pe_ask": 140.2},
        ],
    }


class OptionizeTest(unittest.TestCase):
    def test_long_ce_mapping(self):
        with mock.patch.object(scalper.chain_table, "get_chain", return_value=_fake_chain()):
            o = scalper.optionize("nifty", "LONG", 24215.60, 24204.81, 24237.17)
        self.assertEqual(o["option"], "Buy 24,200 CE")
        self.assertEqual(o["strike"], 24200)
        # entry = ATM CE premium
        self.assertAlmostEqual(o["entry"], 156.0, places=2)
        # stop = entry - loss_spot*delta ; loss_spot = 10.79, delta 0.57
        self.assertAlmostEqual(o["stop"], 156.0 - 10.79 * 0.57, places=1)
        # target = entry + gain_spot*delta ; gain_spot = 21.57
        self.assertAlmostEqual(o["target"], 156.0 + 21.57 * 0.57, places=1)
        self.assertEqual(o["lot_cost"], round(156.0 * 65, 0))

    def test_short_pe_mapping(self):
        with mock.patch.object(scalper.chain_table, "get_chain", return_value=_fake_chain()):
            o = scalper.optionize("nifty", "SHORT", 24215.60, 24226.39, 24194.03)
        self.assertEqual(o["option"], "Buy 24,200 PE")
        self.assertAlmostEqual(o["entry"], 140.0, places=2)
        self.assertAlmostEqual(o["stop"], 140.0 - 10.79 * 0.43, places=1)
        self.assertAlmostEqual(o["target"], 140.0 + 21.57 * 0.43, places=1)

    def test_non_option_asset_returns_none(self):
        self.assertIsNone(scalper.optionize("btc", "LONG", 100, 90, 110))
        self.assertIsNone(scalper.optionize("sensex", "LONG", 100, 90, 110))

    def test_no_entry_returns_none(self):
        self.assertIsNone(scalper.optionize("nifty", "LONG", None, 100, 110))


if __name__ == "__main__":
    unittest.main()
