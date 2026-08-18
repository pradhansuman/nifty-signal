"""Locale tests: alert builders always produce English (Odia locale removed)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".openclaw", "tmp"))

import nifty_server as ns


class LocaleTest(unittest.TestCase):

    def setUp(self):
        self.al = mock.patch.object(ns, "_add_alert")
        self.al.start()
        self.addCleanup(self.al.stop)
        self.old = os.environ.get("TG_LANG")
        self.addCleanup(self._restore)

    def _restore(self):
        if self.old is None:
            os.environ.pop("TG_LANG", None)
        else:
            os.environ["TG_LANG"] = self.old

    def test_default_is_english(self):
        # Odia locale removed — alert text is always English, even without TG_LANG
        os.environ.pop("TG_LANG", None)
        self.assertEqual(ns._t("ନିଫ୍ଟି", "NIFTY"), "NIFTY")

    def test_en_switches(self):
        os.environ["TG_LANG"] = "en"
        self.assertEqual(ns._t("ନିଫ୍ଟି", "NIFTY"), "NIFTY")

    def test_digest_english(self):
        os.environ["TG_LANG"] = "en"
        data = {"day_trade": [{"symbol": "AA", "name": "Aa", "price": 100.0, "day_pct": 3.5,
                               "target": 105.0, "target_pct": 5.0, "vol_ratio": 2.5,
                               "timeline": "today (intraday)", "mom5": 1.0, "trend": "UP"}],
                "swing": [{"symbol": "BB", "name": "Bb", "price": 200.0, "mom5": 4.0,
                           "target": 215.0, "target_pct": 7.5, "trend": "UP",
                           "timeline": "5–10 sessions", "day_pct": 0.5, "vol_ratio": None}]}
        lines = ns._stock_movers_daily_digest(data=data)
        joined = "\n".join(lines)
        self.assertIn("Daily Stock Movers Report", joined)
        self.assertIn("Day Trades:", joined)
        self.assertNotIn("ଦୈନିକ", joined)

    def test_breakout_english(self):
        os.environ["TG_LANG"] = "en"
        data = {"day_trade": [{"symbol": "AA", "name": "Aa", "price": 100.0, "day_pct": 3.5,
                               "target": 105.0, "target_pct": 5.0, "vol_ratio": 2.5,
                               "timeline": "today (intraday)", "mom5": 1.0, "trend": "UP"}]}
        fired = ns._stock_movers_live_alerts(data=data, alerted=set())
        self.assertEqual(fired, 1)
        title, body = ns._add_alert.call_args.args[1], ns._add_alert.call_args.args[2]
        self.assertIn("BREAKOUT", title)
        self.assertIn("Target", body)

    def test_scalp_report_english(self):
        os.environ["TG_LANG"] = "en"
        with mock.patch.object(ns, "_scalp_summary", return_value={
                "by_asset": {}, "net_rs": None, "net_pts": 0, "resolved": 0,
                "wins": 0, "win_rate": 0}):
            out = ns._scalp_daily_report()
        self.assertIn("Daily Scalp Report", out)
        self.assertIn("No scalp calls today.", out)
        self.assertNotIn("ଓଡ଼ିଆ", out)


if __name__ == "__main__":
    unittest.main()
