"""Offline tests: option recorder (snapshot + market-hours gate)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import option_recorder as orc


class OptionRecorderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_base = orc.BASE
        orc.BASE = self.tmp

    def tearDown(self):
        orc.BASE = self._orig_base

    def _fake_chain(self):
        return {
            "error": None, "chain_spot": 24200.0, "expiry": "2026-08-25",
            "rows": [
                {"strike": 24200, "ce_bid": 120.0, "ce_ask": 121.0, "ce_ltp": 120.5,
                 "ce_oi": 1000, "ce_vol": 500, "ce_iv": 13.0, "ce_delta": 0.5,
                 "pe_bid": 130.0, "pe_ask": 131.0, "pe_ltp": 130.5,
                 "pe_oi": 900, "pe_vol": 400, "pe_iv": 14.0, "pe_delta": -0.5},
                {"strike": 24250, "ce_bid": 80.0, "ce_ask": 81.0, "ce_ltp": 80.5,
                 "ce_oi": 800, "ce_vol": 300, "ce_iv": 12.0, "ce_delta": 0.4,
                 "pe_bid": 90.0, "pe_ask": 91.0, "pe_ltp": 90.5,
                 "pe_oi": 700, "pe_vol": 200, "pe_iv": 13.0, "pe_delta": -0.6},
            ],
        }

    def test_snapshot_flat_rows(self):
        with mock.patch("chain_table.get_chain", return_value=self._fake_chain()):
            recs = orc.snapshot("nifty")
        self.assertEqual(len(recs), 2)
        r = recs[0]
        self.assertEqual(r["asset"], "nifty")
        self.assertEqual(r["strike"], 24200)
        self.assertEqual(r["ce_bid"], 120.0)
        self.assertEqual(r["pe_iv"], 14.0)

    def test_record_skips_when_market_closed(self):
        with mock.patch("chain_table.get_chain", return_value=self._fake_chain()):
            with mock.patch.object(orc, "_is_market_open", return_value=False):
                self.assertEqual(orc.record("nifty"), 0)

    def test_record_writes_jsonl(self):
        import datetime
        with mock.patch("chain_table.get_chain", return_value=self._fake_chain()):
            with mock.patch.object(orc, "_is_market_open", return_value=True):
                n = orc.record("nifty")
        self.assertEqual(n, 2)
        day = datetime.datetime.now().strftime("%Y-%m-%d")
        p = orc._path("nifty", day)
        self.assertTrue(os.path.exists(p))
        lines = [ln for ln in open(p).read().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 2)

    def test_is_market_open_weekend(self):
        import datetime
        sat = datetime.datetime(2026, 8, 22, 10, 0)  # Saturday
        self.assertFalse(orc._is_market_open(sat))
        mon = datetime.datetime(2026, 8, 24, 10, 0)  # Monday 10:00
        self.assertTrue(orc._is_market_open(mon))
        early = datetime.datetime(2026, 8, 24, 9, 0)  # before open
        self.assertFalse(orc._is_market_open(early))


if __name__ == "__main__":
    unittest.main()
