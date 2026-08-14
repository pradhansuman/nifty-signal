"""Unit tests for server-side logic: NaN cleaning + scalp call lifecycle."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".openclaw", "tmp"))

import nifty_server as ns


class CleanNanTest(unittest.TestCase):
    def test_nan_and_inf_to_none(self):
        import math
        cleaned = ns._clean_nan({"a": float("nan"), "b": float("inf"), "c": -float("inf"), "d": 5})
        self.assertIsNone(cleaned["a"])
        self.assertIsNone(cleaned["b"])
        self.assertIsNone(cleaned["c"])
        self.assertEqual(cleaned["d"], 5)

    def test_nested_clean(self):
        cleaned = ns._clean_nan({"x": {"y": [float("nan"), 1.5, {"z": float("inf")}]}})
        self.assertIsNone(cleaned["x"]["y"][0])
        self.assertEqual(cleaned["x"]["y"][1], 1.5)
        self.assertIsNone(cleaned["x"]["y"][2]["z"])

    def test_plain_objects_pass_through(self):
        obj = {"a": [1, 2], "b": "text"}
        self.assertEqual(ns._clean_nan(obj), obj)


class ScalpCallLifecycleTest(unittest.TestCase):
    def setUp(self):
        ns._scalp_calls = []
        self.prem = mock.patch.object(ns, "_chain_premium", return_value=100.0)
        self.prem.start()
        self.addCleanup(self.prem.stop)
        # avoid disk writes to the real log during tests
        self.save = mock.patch.object(ns, "_scalp_save_calls")
        self.save.start()
        self.addCleanup(self.save.stop)

    def _call(self, status="ACTIVE", entry=100.0, target=110.0, stop=90.0, expires="23:59"):
        return {"id": 1, "time": "10:00:00", "signal": "SCALP_LONG", "option": "NIFTY 24350 CE",
                "strike": 24350, "option_type": "CE", "entry": entry, "target": target,
                "stop": stop, "expires_at": expires, "status": status}

    def test_target_hit_fires_once(self):
        ns._scalp_calls.append(self._call(target=105.0))  # premium 100 >= ... no wait
        # premium mock returns 100 → target 105 not hit; use target below premium
        ns._scalp_calls = [self._call(target=95.0, stop=50.0)]
        ev = ns._scalp_refresh_statuses()
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0][1], "target")
        self.assertEqual(ns._scalp_calls[0]["status"], "TARGET_HIT")
        # second pass → no duplicate event
        ev2 = ns._scalp_refresh_statuses()
        self.assertEqual(ev2, [])

    def test_stop_hit(self):
        ns._scalp_calls = [self._call(target=150.0, stop=110.0)]  # premium 100 <= 110 → stop
        ev = ns._scalp_refresh_statuses()
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0][1], "stop")
        self.assertEqual(ns._scalp_calls[0]["status"], "STOP_HIT")

    def test_expired(self):
        ns._scalp_calls = [self._call(expires="09:00")]  # now > 09:00 → expired
        ev = ns._scalp_refresh_statuses()
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0][1], "expired")
        self.assertEqual(ns._scalp_calls[0]["status"], "EXPIRED")

    def test_active_untouched_when_in_range(self):
        ns._scalp_calls = [self._call(target=150.0, stop=50.0, expires="23:59")]  # 100 in range
        ev = ns._scalp_refresh_statuses()
        self.assertEqual(ev, [])
        self.assertEqual(ns._scalp_calls[0]["status"], "ACTIVE")

    def test_premium_none_skips(self):
        self.prem.stop()
        p = mock.patch.object(ns, "_chain_premium", return_value=None)
        p.start()
        self.addCleanup(p.stop)
        ns._scalp_calls = [self._call(target=95.0)]
        ev = ns._scalp_refresh_statuses()
        self.assertEqual(ev, [])
        self.assertEqual(ns._scalp_calls[0]["status"], "ACTIVE")

    def test_append_call_caps_at_60(self):
        for i in range(65):
            ns._scalp_append_call("nifty", {"signal": "SCALP_LONG"}, {"option": "O{}".format(i),
                                                              "strike": 24000 + i, "entry": 100.0,
                                                              "target": 110.0, "stop": 90.0,
                                                              "expires_at": "10:30"})
        self.assertEqual(len(ns._scalp_calls), 60)
        self.assertEqual(ns._scalp_calls[0]["option"], "O5")  # oldest dropped
        self.assertTrue(all(c["asset"] == "nifty" for c in ns._scalp_calls))

class ChainPremiumTest(unittest.TestCase):
    def test_chain_premium_resolves_by_strike(self):
        rows = [{"strike": 24350.0, "ce_ltp": 88.5, "pe_ltp": 44.0},
                {"strike": 24400.0, "ce_ltp": 70.0, "pe_ltp": 30.0}]
        with mock.patch("chain_table.get_chain", return_value={"rows": rows}):
            self.assertEqual(ns._chain_premium("nifty", 24350, "CE"), 88.5)
            self.assertEqual(ns._chain_premium("nifty", 24400, "PE"), 30.0)
            self.assertIsNone(ns._chain_premium("nifty", 99999, "CE"))

    def test_spot_asset_uses_scalper_spot(self):
        ns._scalper_caches["btc"] = {"ts": 0, "data": {"spot": 64000.0}}
        self.assertEqual(ns._chain_premium("btc", 0, "CE"), 64000.0)


if __name__ == "__main__":
    unittest.main()


class FiveMinTickTest(unittest.TestCase):
    def test_all_5min_boundaries_match(self):
        for m in ("00", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55"):
            self.assertTrue(ns._is_five_min_tick("12:" + m), m)
        self.assertTrue(ns._is_five_min_tick("09:15"))   # market open
        self.assertTrue(ns._is_five_min_tick("15:25"))   # near close

    def test_off_boundary_does_not_match(self):
        for m in ("01", "02", "07", "13", "44", "59"):
            self.assertFalse(ns._is_five_min_tick("12:" + m), m)

    def test_legacy_endswith_bug_guarded(self):
        # the old .endswith(("00","05")) bug matched ONLY :00/:05 — guard against it
        self.assertTrue(ns._is_five_min_tick("12:10"))
        self.assertTrue(ns._is_five_min_tick("12:45"))


class ScalpPnlTest(unittest.TestCase):
    def test_nifty_long_target_pnl_net_of_spread(self):
        # entry 100 mid, half_spread 1 (buy 101, sell at bid) — target hit at 110
        c = {"asset": "nifty", "signal": "SCALP_LONG", "entry": 100.0, "half_spread": 1.0,
             "hit_premium": 110.0}
        pts, rs, pct = ns._scalp_pnl(c)
        self.assertEqual(pts, 8.0)   # 110 − 100 − 2×1
        self.assertEqual(rs, 8.0 * 65)  # × lot

    def test_nifty_stop_pnl_negative(self):
        c = {"asset": "nifty", "signal": "SCALP_LONG", "entry": 100.0, "half_spread": 1.0,
             "hit_premium": 90.0}
        pts, rs, _ = ns._scalp_pnl(c)
        self.assertEqual(pts, -12.0)  # 90 − 100 − 2 → −12

    def test_btc_long_pnl_direction(self):
        c = {"asset": "btc", "signal": "SCALP_LONG", "entry": 63000.0, "half_spread": 0.0,
             "hit_premium": 63300.0}
        pts, rs, pct = ns._scalp_pnl(c)
        self.assertEqual(pts, 300.0)
        self.assertEqual(rs, 0.0)
        self.assertAlmostEqual(pct, 0.48, places=2)

    def test_btc_short_pnl_direction(self):
        # short wins when price falls
        c = {"asset": "btc", "signal": "SCALP_SHORT", "entry": 63000.0, "half_spread": 0.0,
             "hit_premium": 62700.0}
        pts, _, pct = ns._scalp_pnl(c)
        self.assertEqual(pts, 300.0)
        self.assertAlmostEqual(pct, 0.48, places=2)

    def test_summary_counts(self):
        with mock.patch.object(ns, "_scalp_save_calls"):
            self._summary_test_body()

    def _summary_test_body(self):
        ns._scalp_calls = [
            {"asset": "btc", "signal": "SCALP_SHORT", "entry": 100.0, "half_spread": 0.0,
             "hit_premium": 98.0, "status": "TARGET_HIT"},
            {"asset": "btc", "signal": "SCALP_LONG", "entry": 100.0, "half_spread": 0.0,
             "hit_premium": 95.0, "status": "STOP_HIT"},
            {"asset": "nifty", "signal": "SCALP_LONG", "entry": 100.0, "half_spread": 0.5,
             "hit_premium": 100.0, "status": "ACTIVE"},
        ]
        s = ns._scalp_summary()
        self.assertEqual(s["resolved"], 2)
        self.assertEqual(s["wins"], 1)
        self.assertEqual(s["win_rate"], 50.0)
        self.assertEqual(s["by_asset"]["btc"]["n"], 2)
        self.assertNotIn("nifty", s["by_asset"])  # ACTIVE excluded


class TelegramEscapeTest(unittest.TestCase):
    def test_html_escape_retry(self):
        # Text with raw '<' should still send (escape fallback), not raise
        import telegram_alert as ta
        old = ta.send_telegram
        try:
            ok, err = ta.send_telegram("⚡ test: adx 13 < 25 → WAIT")
            # Either True (sent) or a clean error — never an entity-parse error
            self.assertNotIn("can't parse entities", str(err))
            self.assertIsInstance(ok, bool)
        finally:
            ta.send_telegram = old

    def test_no_op_when_unconfigured(self):
        import telegram_alert as ta
        ok, err = ta.send_telegram("x")
        if not ta._load_config()["token"]:
            self.assertFalse(ok)


class WeeklyReviewTest(unittest.TestCase):
    def test_build_from_dict_shaped_journal(self):
        import weekly_review as wr
        import unittest.mock as mock
        trades = [{"date": "2026-08-12", "pnl": 7327.5, "lots": 3, "strike": "24450",
                   "status": "closed", "direction": "long"}]
        with mock.patch.object(wr, "CACHE_FILE", "/tmp/wr_test_cache.json"):
            with mock.patch.object(wr, "get_all", return_value={"trades": trades, "stats": {}}):
                r = wr.build_weekly_report()
            self.assertEqual(r["trades"], 1)
            self.assertEqual(r["pnl"], 7327.5)
            self.assertEqual(r["win_rate"], 100.0)

    def test_build_from_list_shaped_journal(self):
        import weekly_review as wr
        import unittest.mock as mock
        trades = [{"date": "2026-08-12", "pnl": -500.0, "lots": 1, "strike": "24400",
                   "status": "closed", "direction": "short"}]
        with mock.patch.object(wr, "CACHE_FILE", "/tmp/wr_test_cache.json"):
            with mock.patch.object(wr, "get_all", return_value=trades):
                r = wr.build_weekly_report()
                self.assertEqual(r["trades"], 1)
                self.assertEqual(r["pnl"], -500.0)
                self.assertEqual(r["worst"], -500.0)

    def test_get_weekly_report_refreshes_stale_cache(self):
        import weekly_review as wr
        import unittest.mock as mock
        stale = {"generated": "2026-08-01 00:00", "trades": 0}
        fresh = {"generated": "2026-08-14 14:00", "trades": 1}
        with mock.patch("builtins.open", mock.mock_open(read_data='{"generated": "2026-08-01 00:00", "trades": 0}')):
            with mock.patch.object(wr, "build_weekly_report", return_value=fresh):
                with mock.patch.object(wr, "json") as j:
                    j.load.return_value = stale
                    r = wr.get_weekly_report()
        self.assertEqual(r["trades"], 1)  # stale → rebuilt


class ScalpSpotShortResolutionTest(unittest.TestCase):
    """Spot SHORT calls (BTC/Sensex) must resolve direction-aware:
    TARGET when price falls to/below target, STOP when it rises to/above stop."""

    def setUp(self):
        self.sv = mock.patch.object(ns, "_scalp_save_calls")
        self.sv.start()
        self.addCleanup(self.sv.stop)

    def _call(self, asset, signal, entry, target, stop):
        return {"id": 1, "asset": asset, "signal": signal, "entry": entry,
                "target": target, "stop": stop, "expires_at": "23:59",
                "option_type": "PE", "strike": entry, "status": "ACTIVE"}

    def _patched_save(self):
        return mock.patch.object(ns, "_scalp_save_calls")

    def test_btc_short_not_target_at_entry(self):
        # spot at ~entry (above target) must NOT resolve TARGET
        c = self._call("btc", "SCALP_SHORT", 63000.0, 62685.0, 63315.0)
        ns._scalp_calls = [c]
        with mock.patch.object(ns, "_chain_premium", return_value=63000.0):
            events = ns._scalp_refresh_statuses()
        self.assertEqual(c["status"], "ACTIVE")
        self.assertEqual(events, [])

    def test_btc_short_target_hit_below(self):
        c = self._call("btc", "SCALP_SHORT", 63000.0, 62685.0, 63315.0)
        ns._scalp_calls = [c]
        with mock.patch.object(ns, "_chain_premium", return_value=62685.0):
            events = ns._scalp_refresh_statuses()
        self.assertEqual(c["status"], "TARGET_HIT")
        self.assertEqual(len(events), 1)

    def test_btc_short_stop_hit_above(self):
        c = self._call("btc", "SCALP_SHORT", 63000.0, 62685.0, 63315.0)
        ns._scalp_calls = [c]
        with mock.patch.object(ns, "_chain_premium", return_value=63315.0):
            events = ns._scalp_refresh_statuses()
        self.assertEqual(c["status"], "STOP_HIT")

    def test_nifty_short_premium_convention_unchanged(self):
        # options SHORT (PE) still uses premium convention: target above entry
        c = self._call("nifty", "SCALP_SHORT", 100.0, 110.0, 90.0)
        ns._scalp_calls = [c]
        with mock.patch.object(ns, "_chain_premium", return_value=110.0):
            events = ns._scalp_refresh_statuses()
        self.assertEqual(c["status"], "TARGET_HIT")


class ScalpSignalsOnlyAlertsTest(unittest.TestCase):
    """SCALP_ALERTS_MODE=signals (default): ONLY buy/sell entry alerts fire.
    WAIT/expired/trail/target/stop chatter is suppressed, but watch state and
    call resolution still run (no stale watches)."""

    def _make_watch(self, signal="SCALP_LONG", option="NIFTY 24350 CE", entry=100.0):
        return {"signal": signal, "option": option, "entry": entry, "ts": None,
                "highest": entry, "breakeven": False, "trail": False}

    def test_default_signals_mode_flag(self):
        # default (no env) → verbose off
        self.assertFalse(ns._SCALP_VERBOSE_ALERTS)

    def test_signals_only_still_resolves_calls(self):
        c = {"id": 1, "asset": "nifty", "signal": "SCALP_LONG", "option": "NIFTY 24350 CE",
             "strike": 24350, "option_type": "CE", "entry": 100.0, "target": 110.0,
             "stop": 90.0, "expires_at": "23:59", "status": "ACTIVE"}
        ns._scalp_calls = [c]
        with mock.patch.object(ns, "_scalp_save_calls"), \
             mock.patch.object(ns, "_chain_premium", return_value=110.0):
            events = ns._scalp_refresh_statuses()
        self.assertEqual(c["status"], "TARGET_HIT")  # resolution still runs
        self.assertEqual(len(events), 1)
        self.assertFalse(ns._SCALP_VERBOSE_ALERTS)  # but no alert would be pushed


class OdiaTranslateTest(unittest.TestCase):
    """Odia phrase translation: templates → ଓଡ଼ିଆ, data/HTML untouched."""

    def test_entry_alert_translated(self):
        from telegram_alert import odia_translate
        msg = "🟢 NIFTY SCALP: Buy 24400 CE @ 73.1\nEntry ₹73.1 | Target ₹80.4 | Stop ₹65.8 | Expiry 18-Aug | Lot ₹4,751 | Spread 2.3% | ⏳ expires 14:40"
        out = odia_translate(msg)
        self.assertIn("ସ୍କାଲ୍ପ୍", out)
        self.assertIn("କିଣ", out)
        self.assertIn("ଏଣ୍ଟ୍ରି ₹73.1", out)
        self.assertIn("ଟାର୍ଗେଟ୍ ₹80.4", out)
        self.assertIn("ଷ୍ଟପ୍ ₹65.8", out)
        self.assertIn("ଏକ୍ସପାୟରୀ 18-Aug", out)
        self.assertIn("ସ୍ପ୍ରେଡ୍", out)
        self.assertIn("24400 CE @ 73.1", out)  # ticker data preserved

    def test_perfect_setup_title(self):
        from telegram_alert import odia_translate
        out = odia_translate("🔥 PERFECT SETUP — 🟢 NIFTY SCALP: Buy 24400 CE")
        self.assertIn("ପରଫେକ୍ଟ ସେଟଅପ୍", out)
        self.assertNotIn("PERFECT SETUP", out)

    def test_html_and_numbers_preserved(self):
        from telegram_alert import odia_translate
        msg = "<b>NIFTY signal</b>: score +3, ADX 25, momentum +45.5, below VWAP 24300"
        out = odia_translate(msg)
        self.assertIn("<b>", out)
        self.assertIn("+3", out)
        self.assertIn("45.5", out)
        self.assertIn("ସିଗନାଲ୍", out)
        self.assertIn("ତଳେ", out)

    def test_tg_lang_en_disables(self):
        import os
        old = os.environ.get("TG_LANG")
        os.environ["TG_LANG"] = "en"
        try:
            from telegram_alert import send_telegram
            import telegram_alert
            with mock.patch.object(telegram_alert, "_load_config",
                                   return_value={"token": "x", "chat_id": "1"}), \
                 mock.patch.object(telegram_alert.requests, "post") as mp:
                mp.return_value.status_code = 200
                mp.return_value.json.return_value = {"ok": True}
                send_telegram("🟢 NIFTY SCALP: Buy 24400 CE")
                sent = mp.call_args.kwargs["json"]["text"]
            self.assertIn("NIFTY SCALP", sent)  # untranslated
            self.assertNotIn("ସ୍କାଲ୍ପ୍", sent)
        finally:
            if old is None:
                os.environ.pop("TG_LANG", None)
            else:
                os.environ["TG_LANG"] = old


class ScalpCompactLineTest(unittest.TestCase):
    """Entry alerts use the compact format the user asked for:
    'SELL BTC at ~$62,828 | Stop $63,159 | Target $62,277 | Risk $331/BTC | R:R 1.66'"""

    def test_btc_short_line(self):
        call = {"entry": 62828.0, "stop": 63159.0, "target": 62277.0}
        line = ns._scalp_compact_line("btc", "SCALP_SHORT", call)
        self.assertEqual(line, "SELL BTC at ~$62,828 | Stop $63,159 | Target $62,277 | Risk $331/BTC | R:R 1.66")

    def test_btc_long_line(self):
        call = {"entry": 62828.0, "stop": 62514.0, "target": 63142.0}
        line = ns._scalp_compact_line("btc", "SCALP_LONG", call)
        self.assertEqual(line, "BUY BTC at ~$62,828 | Stop $62,514 | Target $63,142 | Risk $314/BTC | R:R 1.00")

    def test_nifty_option_line_rupees_decimals(self):
        call = {"entry": 73.1, "stop": 65.8, "target": 80.4}
        line = ns._scalp_compact_line("nifty", "SCALP_LONG", call)
        self.assertEqual(line, "BUY NIFTY at ~₹73.1 | Stop ₹65.8 | Target ₹80.4 | Risk ₹7.3/NIFTY | R:R 1.00")

    def test_rr_matches_user_example(self):
        # entry 62828 / stop 63159 / target 62277 → risk 331, rr 551/331 ≈ 1.66
        call = {"entry": 62828.0, "stop": 63159.0, "target": 62277.0}
        line = ns._scalp_compact_line("btc", "SCALP_SHORT", call)
        self.assertIn("R:R 1.66", line)

    def test_odia_translates_compact_line(self):
        from telegram_alert import odia_translate
        line = ns._scalp_compact_line("btc", "SCALP_SHORT",
                                      {"entry": 62828.0, "stop": 63159.0, "target": 62277.0})
        out = odia_translate(line)
        self.assertIn("ବିକ", out)          # SELL
        self.assertIn("ଷ୍ଟପ୍ $63,159", out)  # Stop $
        self.assertIn("ଟାର୍ଗେଟ୍ $62,277", out)
        self.assertIn("ରିସ୍କ୍ $331/BTC", out)
        self.assertIn("R:R 1.66", out)     # untouched
