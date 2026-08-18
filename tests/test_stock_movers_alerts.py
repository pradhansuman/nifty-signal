"""Offline tests for stock-movers Telegram alerts (dedup, thresholds, digest)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".openclaw", "tmp"))

import nifty_server as ns


def _day_row(sym, pct, vr, price=100.0, target=105.0, tpct=5.0):
    return {"symbol": sym, "name": sym.title(), "price": price, "day_pct": pct,
            "vol_ratio": vr, "target": target, "target_pct": tpct,
            "timeline": "today (intraday)", "mom5": 1.0, "trend": "UP"}


class StockMoversAlertTest(unittest.TestCase):

    def setUp(self):
        self.al = mock.patch.object(ns, "_add_alert")
        self.al.start()
        self.addCleanup(self.al.stop)
        self.orig = ns._stock_alerted
        ns._stock_alerted = set()
        self.addCleanup(self._restore)

    def _restore(self):
        ns._stock_alerted = self.orig

    def test_alert_fires_on_big_move_volume(self):
        data = {"day_trade": [_day_row("AA", 3.5, 2.5)]}
        fired = ns._stock_movers_live_alerts(data=data, alerted=ns._stock_alerted)
        self.assertEqual(fired, 1)
        self.assertIn("AA", ns._stock_alerted)
        ns._add_alert.assert_called_once()

    def test_no_alert_below_threshold(self):
        data = {"day_trade": [_day_row("AA", 2.0, 2.5), _day_row("BB", 3.5, 1.2)]}
        fired = ns._stock_movers_live_alerts(data=data, alerted=ns._stock_alerted)
        self.assertEqual(fired, 0)
        ns._add_alert.assert_not_called()

    def test_one_alert_per_symbol_per_day(self):
        data = {"day_trade": [_day_row("AA", 4.0, 3.0)]}
        ns._stock_movers_live_alerts(data=data, alerted=ns._stock_alerted)
        fired2 = ns._stock_movers_live_alerts(data=data, alerted=ns._stock_alerted)
        self.assertEqual(fired2, 0)
        self.assertEqual(ns._add_alert.call_count, 1)

    def test_digest_builds_english_lines(self):
        data = {"day_trade": [_day_row("AA", 3.5, 2.5)],
                "swing": [{"symbol": "BB", "name": "Bb", "price": 200.0, "mom5": 4.0,
                           "target": 215.0, "target_pct": 7.5, "trend": "UP",
                           "timeline": "5–10 sessions", "day_pct": 0.5, "vol_ratio": None}]}
        lines = ns._stock_movers_daily_digest(data=data)
        joined = "\n".join(lines)
        self.assertIn("Daily Stock Movers", joined)
        self.assertIn("Aa", joined)  # shows the NAME, not the symbol
        self.assertIn("🎯", joined)
        ns._add_alert.assert_called_once()

    def test_digest_empty_day(self):
        lines = ns._stock_movers_daily_digest(data={})
        joined = "\n".join(lines)
        self.assertIn("No movers today", joined)


if __name__ == "__main__":
    unittest.main()
