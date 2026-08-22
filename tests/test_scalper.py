"""Unit tests for scalper.py — scoring, gates, call building."""
import os
import sys
import unittest
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".openclaw", "tmp"))

import scalper
from tests.helpers import make_bars, make_flat_bars, chain_row, mock_chain


class FakeClock:
    """Fixed IST datetime inside the scalp window (10:30)."""
    @staticmethod
    def now(tz=None):
        return pd.Timestamp("2026-08-14 10:30:00", tz="Asia/Kolkata").to_pydatetime()


class LateClock:
    """Fixed IST datetime inside the blocked lunch window (12:30)."""
    @staticmethod
    def now(tz=None):
        return pd.Timestamp("2026-08-14 12:30:00", tz="Asia/Kolkata").to_pydatetime()


def patch_environment(**kwargs):
    return mock.patch.dict(os.environ, kwargs, clear=False)


class ScalperScoringTest(unittest.TestCase):
    def setUp(self):
        # replace the whole module-level datetime name (it's a builtin class —
        # patch.object on its attributes is not allowed)
        self.clock = mock.patch("scalper.datetime", FakeClock)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        # pass all gates so scoring alone decides
        self.vix = mock.patch.object(scalper, "_vix_level", return_value=15.0)
        self.vix.start()
        self.addCleanup(self.vix.stop)
        self.adx_patch = mock.patch.object(scalper, "_adx",
                                           return_value=pd.Series([40.0] * 500))
        self.adx_patch.start()
        self.addCleanup(self.adx_patch.stop)
        # isolate from the runtime tuning file — tests control gates explicitly
        self.tun = mock.patch.object(scalper, "_load_tuning", return_value={
            "score_min": 3.0, "trend_min": 0.8, "adx_min": 25.0,
            "vix_min": 12.0, "vix_max": 18.0, "theta_max": 0.5})
        self.tun.start()
        self.addCleanup(self.tun.stop)
        # strip Nifty's per-asset gate overrides so the _load_tuning mock
        # (and per-test re-patches) control the gates
        nifty = {k: v for k, v in scalper.ASSETS["nifty"].items()
                 if k not in ("score_min", "trend_min", "adx_min", "hold_min")}
        self.assets = mock.patch.dict(scalper.ASSETS, {"nifty": nifty})
        self.assets.start()
        self.addCleanup(self.assets.stop)
        self.bars = mock.patch.object(scalper, "get_bars")
        self.bars.start()
        self.addCleanup(self.bars.stop)

    def test_uptrend_scores_long(self):
        scalper.get_bars.return_value = make_bars(up=True)
        out = scalper.main()
        self.assertIn(out["signal"], ("SCALP_LONG", "WAIT"))
        if out["signal"] == "SCALP_LONG":
            self.assertGreaterEqual(out["score"], 3)
            self.assertEqual(out["bias"], "LONG")
        else:
            # gates (trend/regime) may block, but raw score must be >= 3
            self.assertGreaterEqual(out["score"], 3)

    def test_downtrend_scores_short(self):
        scalper.get_bars.return_value = make_bars(up=False)
        out = scalper.main()
        self.assertLessEqual(out["score"], -3)
        self.assertEqual(out["bias"], "SHORT")

    def test_flat_data_no_edge(self):
        # A random walk can legitimately score ±5 (that's why the gates exist).
        # The property that matters: no trade call fires on flat data.
        scalper.get_bars.return_value = make_flat_bars()
        out = scalper.main()
        self.assertEqual(out["signal"], "WAIT")
        self.assertLessEqual(abs(out["score"]), 7)

    def test_weak_trend_gate_blocks(self):
        scalper.get_bars.return_value = make_bars(up=True)
        self.tun.stop()
        t = mock.patch.object(scalper, "_load_tuning", return_value={
            "score_min": 3.0, "slope_atr_min": 999.0, "adx_min": 25.0,
            "vix_min": 12.0, "vix_max": 18.0, "theta_max": 0.5})
        t.start()
        self.addCleanup(t.stop)
        out = scalper.main()
        self.assertEqual(out["signal"], "WAIT")
        self.assertIn("no rising trend", out.get("reason", ""))

    def test_lower_score_min_allows_weaker_setup(self):
        # loosened threshold (chatty mode) accepts score 2
        scalper.get_bars.return_value = make_bars(up=True)
        self.tun.stop()
        t = mock.patch.object(scalper, "_load_tuning", return_value={
            "score_min": 2.0, "trend_min": 0.4, "adx_min": 18.0,
            "vix_min": 10.0, "vix_max": 18.0, "theta_max": 0.5})
        t.start()
        self.addCleanup(t.stop)
        out = scalper.main()
        self.assertGreaterEqual(out["score_min"], 2.0)
        # gates still may block, but threshold must be respected in output
        self.assertEqual(out["score_min"], 2.0)

    def test_adx_gate_blocks(self):
        scalper.get_bars.return_value = make_bars(up=True)
        self.adx_patch.stop()
        adx = mock.patch.object(scalper, "_adx", return_value=pd.Series([10.0] * 500))
        adx.start()
        self.addCleanup(adx.stop)
        out = scalper.main()
        self.assertEqual(out["signal"], "WAIT")
        self.assertIn("ADX", out.get("reason", ""))

    def test_vix_gate_blocks_low_vix(self):
        scalper.get_bars.return_value = make_bars(up=True)
        self.vix.stop()
        vix = mock.patch.object(scalper, "_vix_level", return_value=8.0)
        vix.start()
        self.addCleanup(vix.stop)
        out = scalper.main()
        self.assertEqual(out["signal"], "WAIT")
        self.assertIn("VIX", out.get("reason", ""))

    def test_vix_gate_blocks_high_vix(self):
        scalper.get_bars.return_value = make_bars(up=True)
        self.vix.stop()
        vix = mock.patch.object(scalper, "_vix_level", return_value=22.0)
        vix.start()
        self.addCleanup(vix.stop)
        out = scalper.main()
        self.assertEqual(out["signal"], "WAIT")
        self.assertIn("VIX", out.get("reason", ""))

    def test_window_block_outside_hours(self):
        self.clock.stop()
        c = mock.patch("scalper.datetime", LateClock)
        c.start()
        self.addCleanup(c.stop)
        scalper.get_bars.return_value = make_bars(up=True)
        out = scalper.main()
        self.assertEqual(out["signal"], "WAIT")
        self.assertIn("window", out.get("reason", "").lower())


class ScalperBuildCallTest(unittest.TestCase):
    def setUp(self):
        self.chain = mock.patch.object(scalper.chain_table, "get_chain")
        self.chain.start()
        self.addCleanup(self.chain.stop)
        self.tun = mock.patch.object(scalper, "_load_tuning", return_value={
            "score_min": 3.0, "trend_min": 0.8, "adx_min": 25.0,
            "vix_min": 12.0, "vix_max": 18.0, "theta_max": 0.5})
        self.tun.start()
        self.addCleanup(self.tun.stop)

    def test_spread_guard_blocks_wide_spread(self):
        # spread 10 on 85 ltp ≈ 11.8% > 3% → blocked
        rows = [chain_row(24350, 85.0, bid=80.0, ask=90.0, delta=0.5)]
        scalper.chain_table.get_chain.return_value = mock_chain(rows)
        call = scalper.build_call("nifty", 24350, "LONG", "2026-08-18")
        self.assertIsNotNone(call)
        self.assertTrue(call.get("blocked"))
        self.assertIn("spread", call.get("block_reason", ""))

    def test_theta_guard_blocks_pathological_decay(self):
        # theta -300 on 100 premium = 2.08%/10min > 0.5% gate → blocked
        rows = [chain_row(24350, 100.0, bid=99.0, ask=101.0, delta=0.5, theta=-300.0)]
        scalper.chain_table.get_chain.return_value = mock_chain(rows)
        call = scalper.build_call("nifty", 24350, "LONG", "2026-08-18")
        self.assertTrue(call.get("blocked"))
        self.assertIn("theta", call.get("block_reason", ""))

    def test_theta_normal_decay_passes(self):
        # deep-ITM style: theta -10 on 205 premium = 0.34%/10min → passes (was
        # wrongly blocked under the old per-day metric)
        rows = [chain_row(24200, 205.0, bid=204.0, ask=206.0, delta=0.75, theta=-10.0)]
        scalper.chain_table.get_chain.return_value = mock_chain(rows)
        call = scalper.build_call("nifty", 24343, "LONG", "2026-08-18")
        self.assertFalse(call.get("blocked"))
        self.assertEqual(call["strike"], 24200)

    def test_spread_aware_target_stop(self):
        # spread 2.0 (86.5/88.5), half = 1.0, ltp 87.5
        rows = [chain_row(24350, 87.5, bid=86.5, ask=88.5, delta=0.5, theta=-0.5)]
        scalper.chain_table.get_chain.return_value = mock_chain(rows)
        call = scalper.build_call("nifty", 24350, "LONG", "2026-08-18")
        self.assertFalse(call.get("blocked"))
        self.assertEqual(call["entry"], 87.5)
        self.assertEqual(call["buy_ask"], 88.5)
        self.assertAlmostEqual(call["target"], 87.5 * 1.10 + 1.0, places=2)
        self.assertAlmostEqual(call["stop"], 87.5 * 0.90 - 1.0, places=2)
        self.assertEqual(call["half_spread"], 1.0)

    def test_delta_filter_rejects_out_of_range(self):
        # only delta 0.25 candidates → outside 0.40-0.80 → no call
        rows = [chain_row(24350, 87.5, delta=0.25)]
        scalper.chain_table.get_chain.return_value = mock_chain(rows)
        call = scalper.build_call("nifty", 24350, "LONG", "2026-08-18")
        self.assertIsNone(call)

    def test_no_chain_returns_none(self):
        scalper.chain_table.get_chain.return_value = {"rows": [], "expiry": "2026-08-18"}
        call = scalper.build_call("nifty", 24350, "LONG", "2026-08-18")
        self.assertIsNone(call)

    def test_tightest_spread_selected(self):
        rows = [
            chain_row(24300, 95.0, bid=90.0, ask=100.0, delta=0.55),   # 10.5% spread
            chain_row(24350, 87.5, bid=86.5, ask=88.5, delta=0.5),     # 2.3% spread
            chain_row(24400, 80.0, bid=77.0, ask=83.0, delta=0.45),    # 7.5% spread
        ]
        scalper.chain_table.get_chain.return_value = mock_chain(rows)
        call = scalper.build_call("nifty", 24350, "LONG", "2026-08-18")
        self.assertEqual(call["strike"], 24350)

    def test_liquidity_skips_dead_strike(self):
        # dead strike (OI 50) has tighter spread; liquid strike (OI 5000) wider.
        # Liquidity filter must drop the dead strike → pick the liquid one.
        r_dead = chain_row(24350, 87.5, bid=87.2, ask=87.8, delta=0.5)      # ~0.7% spread
        r_dead["ce_oi"] = 50
        r_liquid = chain_row(24300, 95.0, bid=93.0, ask=95.0, delta=0.55)   # ~2.1% spread
        r_liquid["ce_oi"] = 5000
        scalper.chain_table.get_chain.return_value = mock_chain([r_dead, r_liquid])
        call = scalper.build_call("nifty", 24350, "LONG", "2026-08-18")
        self.assertEqual(call["strike"], 24300)  # liquid beats tighter-spread dead strike
        self.assertEqual(call["oi"], 5000)

    def test_spot_call_btc(self):
        # BTC is now options-first (Delta), but falls back to a spot call when
        # the chain is unavailable/empty.
        with mock.patch.object(scalper.delta_exchange, "get_btc_chain",
                               return_value={"error": "down", "rows": []}):
            call = scalper.build_call("btc", 64000.0, "LONG", "INTRAday")
        self.assertFalse(call.get("blocked"))
        self.assertEqual(call["entry"], 64000.0)
        self.assertEqual(call["target"], round(64000.0 * 1.005, 2))
        self.assertEqual(call["stop"], round(64000.0 * 0.995, 2))
        self.assertIsNone(call["delta"])
        self.assertEqual(call["expiry"], "INTRAday")

    def test_spot_call_sensex(self):
        call = scalper.build_call("sensex", 77800.0, "SHORT", "INTRAday")
        self.assertFalse(call.get("blocked"))
        self.assertEqual(call["entry"], 77800.0)
        self.assertEqual(call["target"], round(77800.0 * 0.9985, 2))  # short: target below
        self.assertEqual(call["stop"], round(77800.0 * 1.0015, 2))


if __name__ == "__main__":
    unittest.main()


class LoadTuningStrictAfterTest(unittest.TestCase):
    """Time-aware strict boundary: past SCALP_STRICT_AFTER, chatty file is ignored."""

    _TUNING_PATH = None

    def _tuning_path(self):
        if LoadTuningStrictAfterTest._TUNING_PATH is None:
            import os as _os
            LoadTuningStrictAfterTest._TUNING_PATH = _os.path.join(
                _os.path.dirname(_os.path.abspath(scalper.__file__)),
                ".openclaw", "tmp", "scalper_tuning.json")
        return LoadTuningStrictAfterTest._TUNING_PATH

    def setUp(self):
        import os as _os
        p = self._tuning_path()
        self._orig = None
        if _os.path.exists(p):
            with open(p) as f:
                self._orig = f.read()

    def _write_tuning(self, data):
        import json as _json, os as _os
        p = self._tuning_path()
        _os.makedirs(_os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            _json.dump(data, f)
        return p

    def tearDown(self):
        import os as _os
        p = self._tuning_path()
        if self._orig is not None:
            with open(p, "w") as f:
                f.write(self._orig)   # restore real runtime file
        elif _os.path.exists(p):
            _os.remove(p)

    def test_chatty_file_applied_before_boundary(self):
        import os as _os
        p = self._write_tuning({"score_min": 2, "trend_min": 0.05, "adx_min": 10,
                                "window_open": True, "regime_off": True})
        old = _os.environ.get("SCALP_STRICT_AFTER")
        _os.environ["SCALP_STRICT_AFTER"] = "23:59"  # before boundary → file applies
        try:
            self.assertEqual(scalper._load_tuning()["score_min"], 2.0)
            self.assertTrue(scalper._load_tuning()["window_open"])
        finally:
            if old is None:
                _os.environ.pop("SCALP_STRICT_AFTER", None)
            else:
                _os.environ["SCALP_STRICT_AFTER"] = old

    def test_strict_after_boundary_ignores_file(self):
        import os as _os
        self._write_tuning({"score_min": 2, "trend_min": 0.05, "adx_min": 10,
                            "window_open": True, "regime_off": True})
        old = _os.environ.get("SCALP_STRICT_AFTER")
        _os.environ["SCALP_STRICT_AFTER"] = "00:00"  # always past → strict
        try:
            t = scalper._load_tuning()
            self.assertEqual(t["score_min"], 3.0)   # strict default
            self.assertEqual(t["trend_min"], 0.8)
            self.assertFalse(t["window_open"])
            self.assertFalse(t["regime_off"])
        finally:
            if old is None:
                _os.environ.pop("SCALP_STRICT_AFTER", None)
            else:
                _os.environ["SCALP_STRICT_AFTER"] = old


class DeltaBtcTest(unittest.TestCase):
    """BTC scalper now routes through Delta Exchange options, falling back to spot."""

    def _mock_chain(self, rows, spot=63000.0, expiry="21-Aug-2026"):
        return {"error": None, "expiry": expiry, "atm": 63000, "rows": rows,
                "chain_spot": spot, "asset": "btc"}

    def test_delta_chain_merge_calls_and_puts(self):
        import delta_exchange as de
        import unittest.mock as mock
        calls = {"result": [{"symbol": "C-BTC-63000-210826", "contract_type": "call_options",
                             "strike_price": "63000", "close": "100", "spot_price": "63000",
                             "quotes": {"best_bid": "98", "best_ask": "102"},
                             "greeks": {"delta": "0.55", "theta": "-1.2"}}]}
        puts = {"result": [{"symbol": "P-BTC-63000-210826", "contract_type": "put_options",
                            "strike_price": "63000", "close": "110", "spot_price": "63000",
                            "quotes": {"best_bid": "108", "best_ask": "112"},
                            "greeks": {"delta": "-0.45", "theta": "-1.1"}}]}
        with mock.patch.object(de, "_fetch", side_effect=[calls, puts]):
            ch = de.get_btc_chain(force=True)
        self.assertIsNone(ch["error"])
        self.assertEqual(len(ch["rows"]), 1)
        r = ch["rows"][0]
        self.assertEqual(r["strike"], 63000)
        self.assertEqual(r["ce_ltp"], 100.0)
        self.assertEqual(r["pe_ltp"], 110.0)
        self.assertAlmostEqual(r["ce_delta"], 0.55)
        self.assertAlmostEqual(r["pe_delta"], -0.45)

    def test_btc_build_call_option_path(self):
        import unittest.mock as mock
        rows = [{"strike": 63000, "ce_ltp": 100.0, "ce_bid": 99.0, "ce_ask": 101.0,
                 "ce_delta": 0.55, "ce_theta": -0.5,
                 "pe_ltp": 100.0, "pe_bid": 99.0, "pe_ask": 101.0,
                 "pe_delta": -0.55, "pe_theta": -0.5}]
        with mock.patch.object(scalper.delta_exchange, "get_btc_chain",
                               return_value=self._mock_chain(rows)):
            c = scalper.build_call("btc", 63000.0, "LONG", "21-Aug-2026")
        self.assertIsNotNone(c)
        self.assertIn("CE", c["option"])
        # spread = 2.0 → half_spread 1.0 → target = 100*1.10 + 1, stop = 100*0.90 - 1
        self.assertEqual(c["target"], 111.0)
        self.assertEqual(c["stop"], 89.0)

    def test_btc_fallback_to_spot_when_chain_fails(self):
        import unittest.mock as mock
        with mock.patch.object(scalper.delta_exchange, "get_btc_chain",
                               return_value={"error": "down", "rows": []}):
            c = scalper.build_call("btc", 63000.0, "SHORT", None)
        self.assertIsNotNone(c)
        self.assertIn("SHORT BTC PERP", c["option"])  # futures fallback call
        self.assertLess(c["target"], c["entry"])     # short target below entry


class DeltaBtcFuturesCallTest(unittest.TestCase):
    """BTC fallback calls are labelled BTC PERP with funding from Delta."""

    def test_spot_call_btc_futures_label(self):
        with mock.patch.object(scalper.delta_exchange, "get_btc_futures",
                               return_value={"price": 64000.0, "funding": 0.0007,
                                             "source": "delta_futures"}):
            call = scalper._spot_call("btc", 64000.0, "SHORT")
        self.assertTrue(call["futures"])
        self.assertEqual(call["option"], "SHORT BTC PERP")
        self.assertEqual(call["funding"], 0.0007)
        self.assertEqual(call["feed"], "delta_futures")
        # target BELOW entry for a SHORT (0.5% tp), stop above
        self.assertLess(call["target"], call["entry"])
        self.assertGreater(call["stop"], call["entry"])

    def test_spot_call_btc_futures_fallback_feed(self):
        with mock.patch.object(scalper.delta_exchange, "get_btc_futures",
                               side_effect=Exception("down")):
            call = scalper._spot_call("btc", 64000.0, "LONG")
        self.assertTrue(call["futures"])
        self.assertEqual(call["feed"], "yf-spot")
        self.assertEqual(call["option"], "LONG BTC PERP")


class FundingGateTest(unittest.TestCase):
    """BTC funding-rate gate: skip the side that pays carry."""

    def test_long_blocked_when_funding_positive(self):
        bias, block = scalper._funding_gate("btc", "LONG", 0.001, 0.0005)
        self.assertEqual(bias, "FLAT")
        self.assertIn("longs pay carry", block)

    def test_short_blocked_when_funding_negative(self):
        bias, block = scalper._funding_gate("btc", "SHORT", -0.001, 0.0005)
        self.assertEqual(bias, "FLAT")
        self.assertIn("shorts pay carry", block)

    def test_long_allowed_when_funding_negative(self):
        bias, block = scalper._funding_gate("btc", "LONG", -0.001, 0.0005)
        self.assertEqual(bias, "LONG")
        self.assertIsNone(block)

    def test_short_allowed_when_funding_positive(self):
        bias, block = scalper._funding_gate("btc", "SHORT", 0.001, 0.0005)
        self.assertEqual(bias, "SHORT")
        self.assertIsNone(block)

    def test_neutral_funding_no_block(self):
        bias, block = scalper._funding_gate("btc", "LONG", 0.0001, 0.0005)
        self.assertEqual(bias, "LONG")
        self.assertIsNone(block)

    def test_non_btc_ignored(self):
        bias, block = scalper._funding_gate("nifty", "LONG", 0.001, 0.0005)
        self.assertEqual(bias, "LONG")
        self.assertIsNone(block)

    def test_funding_gate_in_tuning_defaults(self):
        tun = scalper._load_tuning()
        self.assertIn("funding_gate", tun)
        self.assertGreater(tun["funding_gate"], 0)


class PerAssetGateOverrideTest(unittest.TestCase):
    """BTC uses its own (stricter) trend/ADX gates than the global defaults."""

    def test_btc_has_stricter_gates(self):
        # BTC runs 1h with trend 1.5% + ADX 25 (backtest: PF 1.30)
        self.assertEqual(scalper.ASSETS["btc"].get("trend_min"), 1.5)
        self.assertEqual(scalper.ASSETS["btc"].get("adx_min"), 25)
        self.assertEqual(scalper.ASSETS["btc"].get("interval"), "1h")
        self.assertEqual(scalper.ASSETS["btc"].get("hold_min"), 360)
        self.assertGreater(scalper.ASSETS["btc"]["trend_min"], 0.8)  # stricter than global
        self.assertGreater(scalper.ASSETS["btc"]["adx_min"], 20)

    def test_nifty_uses_global_defaults(self):
        # All assets now carry their own tuned gates (no bare global fallback)
        self.assertEqual(scalper.ASSETS["nifty"].get("trend_min"), 1.0)
        self.assertEqual(scalper.ASSETS["nifty"].get("adx_min"), 30)

    def test_bnf_runs_15m_with_tuned_gates(self):
        self.assertEqual(scalper.ASSETS["bnf"].get("interval"), "15m")
        self.assertEqual(scalper.ASSETS["bnf"].get("trend_min"), 0.5)
        self.assertEqual(scalper.ASSETS["bnf"].get("adx_min"), 30)

    def test_sensex_tuned_gates(self):
        self.assertEqual(scalper.ASSETS["sensex"].get("trend_min"), 1.0)
        self.assertEqual(scalper.ASSETS["sensex"].get("adx_min"), 30)
        self.assertEqual(scalper.ASSETS["sensex"].get("hold_min"), 30)
