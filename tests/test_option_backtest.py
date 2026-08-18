"""Offline tests for the option P&L backtest engine (no network / no files).

Exercises the trade-execution math (bid/ask + slippage + full cost model),
MFE/MAE, S/R filter, RVOL, expectancy, and the end-to-end pipeline with mocked
data loading + signal generation.
"""
import os
import sys
import unittest
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import option_backtest as ob
from cost_model import round_trip_cost

LOT = 65


def _row(strike, spot, side, ltp, bid=None, ask=None, oi=1000, vol=10000, delta=0.55):
    r = {"strike": strike, "spot": spot}
    b = bid if bid is not None else ltp * 0.995
    a = ask if ask is not None else ltp * 1.005
    for s in ("CE", "PE"):
        pre = s.lower()
        r[f"{pre}_ltp"] = ltp
        r[f"{pre}_bid"] = b
        r[f"{pre}_ask"] = a
        r[f"{pre}_oi"] = oi
        r[f"{pre}_vol"] = vol
        r[f"{pre}_delta"] = delta if s == "CE" else -delta
    return r


def _lookup_for(minutes, ltp_seq, strike=24200, side=1):
    """Build a minute→{strike:row} lookup whose CE ltp follows ltp_seq."""
    lookup = {}
    for m, ltp in zip(minutes, ltp_seq):
        lookup[m] = {strike: _row(strike, 24200, side, ltp, bid=ltp * 0.99, ask=ltp * 1.01)}
    return lookup


class TradeExecutionTest(unittest.TestCase):
    def _minutes(self, n):
        return [pd.Timestamp("2026-08-18 10:00") + pd.Timedelta(minutes=k) for k in range(n)]

    def test_target_hit_net_positive(self):
        # premium 100 → target +10% = 110; path crosses it
        minutes = self._minutes(6)
        ltp_seq = [100, 102, 108, 111, 112, 113]
        lookup = _lookup_for(minutes, ltp_seq)
        p = dict(ob.DEFAULTS); p["lot"] = LOT
        t = ob.run_option_trade(lookup, minutes, 0, 1, 24200, p)
        self.assertIsNotNone(t)
        self.assertEqual(t["reason"], "TARGET")
        # entry = ask(101) + slip(0.1) = 101.1 ; exit at bid(111*0.99) - slip
        self.assertAlmostEqual(t["entry"], 101.0 + 0.1, places=2)
        self.assertGreater(t["net"], 0)
        # net == gross - cost exactly
        self.assertAlmostEqual(t["net"], round(t["gross"] - t["cost"], 2), places=2)
        self.assertGreater(t["mfe"], 0)

    def test_stop_hit_net_negative(self):
        minutes = self._minutes(6)
        ltp_seq = [100, 98, 95, 90, 88, 87]
        lookup = _lookup_for(minutes, ltp_seq)
        p = dict(ob.DEFAULTS); p["lot"] = LOT
        t = ob.run_option_trade(lookup, minutes, 0, 1, 24200, p)
        self.assertEqual(t["reason"], "STOP")
        self.assertLess(t["net"], 0)
        self.assertGreater(t["mae"], 0)

    def test_time_stop_flat(self):
        minutes = self._minutes(6)
        ltp_seq = [100, 100, 100, 100, 100, 100]
        lookup = _lookup_for(minutes, ltp_seq)
        p = dict(ob.DEFAULTS); p["lot"] = LOT; p["hold_min"] = 5
        t = ob.run_option_trade(lookup, minutes, 0, 1, 24200, p)
        self.assertEqual(t["reason"], "TIME")
        # flat price → tiny spread+cost loss, MFE/MAE ≈ 0
        self.assertLess(t["net"], 0)
        self.assertAlmostEqual(t["mfe"], 0.0, places=1)
        self.assertAlmostEqual(t["mae"], 0.0, places=1)

    def test_cost_matches_model(self):
        minutes = self._minutes(6)
        ltp_seq = [100, 105, 110, 111, 112, 113]
        lookup = _lookup_for(minutes, ltp_seq)
        p = dict(ob.DEFAULTS); p["lot"] = LOT
        t = ob.run_option_trade(lookup, minutes, 0, 1, 24200, p)
        expect_cost = round_trip_cost(t["entry"], t["exit"], LOT)
        self.assertAlmostEqual(t["cost"], round(expect_cost, 2), places=1)

    def test_bid_ask_slippage(self):
        # entry must be ask+slippage, exit bid−slippage
        minutes = self._minutes(3)
        ltp = [100, 100, 100]
        strike = 24200
        lookup = {}
        for m, l in zip(minutes, ltp):
            lookup[m] = {strike: _row(strike, 24200, 1, l, bid=99.0, ask=101.0)}
        p = dict(ob.DEFAULTS); p["lot"] = LOT; p["slippage_rs"] = 0.5; p["hold_min"] = 2
        t = ob.run_option_trade(lookup, minutes, 0, 1, strike, p)
        self.assertAlmostEqual(t["entry"], 101.0 + 0.5, places=2)
        self.assertAlmostEqual(t["exit"], 99.0 - 0.5, places=2)


class FilterTest(unittest.TestCase):
    def test_sr_levels(self):
        df = pd.DataFrame({
            "High": [100, 102, 101], "Low": [98, 99, 97], "Close": [99, 101, 100],
        })
        r1, s1 = ob.sr_levels(df, 2)
        h, l, c = 102.0, 97.0, 100.0
        p = (h + l + c) / 3
        self.assertAlmostEqual(r1, 2 * p - l, places=6)
        self.assertAlmostEqual(s1, 2 * p - h, places=6)

    def test_sr_blocked_long_under_resistance(self):
        self.assertTrue(ob.sr_blocked(1, 99, 100, 95, 5))    # 99 within 5 of R1=100
        self.assertFalse(ob.sr_blocked(1, 90, 100, 95, 5))   # far below
        self.assertTrue(ob.sr_blocked(-1, 96, 100, 95, 5))   # 96 within 5 of S1=95

    def test_chain_activity_rvol(self):
        # cumulative volumes double in the last minute → RVOL > 1
        minutes = [pd.Timestamp("2026-08-18 10:00") + pd.Timedelta(minutes=k) for k in range(5)]
        rows = []
        cum = [1000, 1200, 1400, 1600, 2600]  # last minute spikes
        for m, cv in zip(minutes, cum):
            for strike in (24100, 24200):
                rows.append({"minute": m, "strike": strike, "spot": 24200,
                             "ce_vol": cv, "pe_vol": cv, "ce_oi": 1, "pe_oi": 1,
                             "expiry": "2026-08-25"})
        df = pd.DataFrame(rows)
        rv = ob.chain_activity(df, minutes[-1], window=3)
        self.assertIsNotNone(rv)
        self.assertGreater(rv, 1.0)


    def test_select_strike_skips_when_no_delta_eligible(self):
        # all deltas outside 0.40–0.80 → must NOT fall back to nearest strike
        minute = pd.Timestamp("2026-08-18 10:00")
        lookup = {minute: {
            24200: {"strike": 24200, "spot": 24200, "ce_delta": 0.95},
            24250: {"strike": 24250, "spot": 24200, "ce_delta": 0.15},
        }}
        strike, row = ob._select_strike(lookup, minute, 1, 24200.0, 0.40, 0.80)
        self.assertIsNone(strike)
        self.assertIsNone(row)

    def test_select_strike_picks_delta_eligible(self):
        minute = pd.Timestamp("2026-08-18 10:00")
        lookup = {minute: {
            24200: {"strike": 24200, "spot": 24200, "ce_delta": 0.55},
            24250: {"strike": 24250, "spot": 24200, "ce_delta": 0.30},
        }}
        strike, row = ob._select_strike(lookup, minute, 1, 24200.0, 0.40, 0.80)
        self.assertEqual(strike, 24200)


class ExpectancyTest(unittest.TestCase):
    def test_expectancy_math(self):
        trades = [
            {"net": 100.0, "mfe": 5.0, "mae": 2.0},
            {"net": -50.0, "mfe": 3.0, "mae": 4.0},
            {"net": 40.0, "mfe": 6.0, "mae": 1.0},
        ]
        e = ob._expectancy(trades)
        self.assertEqual(e["n"], 3)
        self.assertAlmostEqual(e["wr"], 2 / 3, places=6)
        self.assertAlmostEqual(e["net"], 90.0, places=2)
        self.assertAlmostEqual(e["ev"], 30.0, places=2)
        # gw = 70, gl = 50, pf = 140/50
        self.assertAlmostEqual(e["gw"], 70.0, places=2)
        self.assertAlmostEqual(e["gl"], 50.0, places=2)
        self.assertAlmostEqual(e["pf"], 2.8, places=2)


class PipelineTest(unittest.TestCase):
    def test_backtest_end_to_end(self):
        """Mock load_chain + generate_signals → verify trades, costs, split."""
        minutes = [pd.Timestamp("2026-08-18 10:00") + pd.Timedelta(minutes=k) for k in range(30)]
        spot = pd.Series([24200.0] * 30, index=minutes)
        lookup = {m: {24200: _row(24200, 24200, 1, 100.0)} for m in minutes}

        df = pd.DataFrame([{"minute": m, "strike": 24200, "spot": 24200.0,
                            "ce_ltp": 100.0, "ce_bid": 99.0, "ce_ask": 101.0,
                            "ce_oi": 1000, "ce_vol": 10000, "ce_delta": 0.55,
                            "pe_ltp": 100.0, "pe_bid": 99.0, "pe_ask": 101.0,
                            "pe_oi": 1000, "pe_vol": 10000, "pe_delta": -0.55,
                            "expiry": "2026-08-25"} for m in minutes])
        signals = [
            {"ts": minutes[1], "side": 1, "score": 4, "spot": 24200.0},
            {"ts": minutes[20], "side": -1, "score": -4, "spot": 24200.0},
        ]
        with mock.patch.object(ob, "load_chain", return_value=(df, minutes, spot)), \
             mock.patch.object(ob, "generate_signals", return_value=signals):
            trades, meta = ob.backtest("nifty", filters={})
        self.assertEqual(meta["trades"], 2)
        self.assertEqual(len(trades), 2)
        # each trade must carry NET and cost
        for t in trades:
            self.assertIn("net", t)
            self.assertIn("cost", t)
            self.assertIn("split", t)
            self.assertIn("reason", t)
        # walk-forward split present (train + test)
        splits = {t["split"] for t in trades}
        self.assertTrue(splits & {"train", "test"})


if __name__ == "__main__":
    unittest.main()
