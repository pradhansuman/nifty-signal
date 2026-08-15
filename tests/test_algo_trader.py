"""Unit tests for algo_trader.py — dry-run orders, guards, instrument keys."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".openclaw", "tmp"))

import algo_trader


class AlgoTraderTest(unittest.TestCase):
    def setUp(self):
        # isolate config + order log in a temp dir
        self.tmp = tempfile.mkdtemp()
        self.cfg_patch = mock.patch.object(algo_trader, "CONFIG_PATH",
                                           os.path.join(self.tmp, "algo_config.json"))
        self.log_patch = mock.patch.object(algo_trader, "ALGO_LOG_PATH",
                                           os.path.join(self.tmp, "algo_orders.json"))
        self.cfg_patch.start()
        self.log_patch.start()
        self.addCleanup(self.cfg_patch.stop)
        self.addCleanup(self.log_patch.stop)
        # fresh in-memory state (today = CURRENT date — hardcoding a past date
        # makes load_state() reset the state and wipe the flags mid-test)
        from datetime import datetime as _dt
        algo_trader._algo_state = {k: (0 if k not in ("active_positions", "closed_trades") else [])
                                   for k in ("today", "trades_today", "lots_today", "pnl_today",
                                             "active_positions", "closed_trades", "daily_limit_hit")}
        algo_trader._algo_state["today"] = _dt.now().strftime("%Y-%m-%d")
        # ensure a known config (all strategies enabled, dry-run)
        cfg = dict(algo_trader.DEFAULT_CONFIG)
        cfg["live_mode"] = False
        for k in cfg["enabled_strategies"]:
            cfg["enabled_strategies"][k] = True
        algo_trader.save_config(cfg)

    def _cfg(self):
        with open(algo_trader.CONFIG_PATH) as f:
            return json.load(f)

    def test_dry_run_order(self):
        res = algo_trader.execute_trade("ema_bounce", "BUY", 24350, "2026-08-18", 1, 88.5, "CE")
        self.assertEqual(res["status"], "dry_run")
        self.assertIn("DRY RUN", res.get("message", ""))
        order = res["order"]
        self.assertEqual(order["quantity"], 65)          # Nifty lot
        self.assertEqual(order["instrument"], "NIFTY 24350 CE")
        self.assertEqual(order["order_type"], "MARKET")

    def test_dry_run_writes_log(self):
        algo_trader.execute_trade("orb", "BUY", 24400, "2026-08-18", 1, 70.0, "CE")
        self.assertTrue(os.path.exists(algo_trader.ALGO_LOG_PATH))
        with open(algo_trader.ALGO_LOG_PATH) as f:
            logs = json.load(f)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["signal_type"], "orb")
        self.assertFalse(logs[0].get("live"))

    def test_disabled_strategy_blocked(self):
        cfg = self._cfg()
        cfg["enabled_strategies"]["ema_bounce"] = False
        algo_trader.save_config(cfg)
        res = algo_trader.execute_trade("ema_bounce", "BUY", 24350, "2026-08-18", 1, 88.5, "CE")
        self.assertEqual(res["status"], "blocked")
        self.assertIn("not enabled", res.get("reason", ""))

    def test_daily_loss_limit_blocks(self):
        algo_trader._algo_state["daily_limit_hit"] = True  # flag set when limit breached
        res = algo_trader.execute_trade("ema_bounce", "BUY", 24350, "2026-08-18", 1, 88.5, "CE")
        self.assertEqual(res["status"], "blocked")
        self.assertIn("loss limit", res.get("reason", ""))

    def test_max_lots_per_day_blocks(self):
        algo_trader._algo_state["lots_today"] = 10
        res = algo_trader.execute_trade("ema_bounce", "BUY", 24350, "2026-08-18", 1, 88.5, "CE")
        self.assertEqual(res["status"], "blocked")
        self.assertIn("daily lots", res.get("reason", ""))

    def test_max_lots_per_trade_blocks(self):
        res = algo_trader.execute_trade("ema_bounce", "BUY", 24350, "2026-08-18", 5, 88.5, "CE")
        self.assertEqual(res["status"], "blocked")
        self.assertIn("per trade", res.get("reason", ""))

    def test_unknown_strategy_blocked(self):
        res = algo_trader.execute_trade("no_such_strategy", "BUY", 24350, "2026-08-18", 1, 88.5, "CE")
        self.assertEqual(res["status"], "blocked")

    def test_instrument_key_from_chain(self):
        rows = [{"strike": 24350.0, "ce_key": "NSE_FO|45104", "pe_key": "NSE_FO|45105"}]
        with mock.patch("chain_table.get_chain",
                               return_value={"rows": rows, "expiry": "2026-08-18"}):
            key = algo_trader._instrument_key(24350, "CE", "2026-08-18")
            self.assertEqual(key, "NSE_FO|45104")
            key_pe = algo_trader._instrument_key(24350, "PE", "2026-08-18")
            self.assertEqual(key_pe, "NSE_FO|45105")

    def test_instrument_key_fallback_compound(self):
        with mock.patch("chain_table.get_chain", return_value={"rows": [], "expiry": "2026-08-18"}):
            key = algo_trader._instrument_key(24350, "CE", "2026-08-18")
            self.assertEqual(key, "NSE_FO|NIFTY|24350|CE|18-AUG-2026")

    def test_trading_token_prefers_oauth(self):
        with mock.patch.object(algo_trader, "_get_trading_token", return_value="oauth-token-123"):
            self.assertEqual(algo_trader._get_trading_token(), "oauth-token-123")


if __name__ == "__main__":
    unittest.main()
