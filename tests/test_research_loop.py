"""Tests for research_loop.py — the frozen-strategy validation pipeline.

Covers the two NEW pure stages: clean_dataset (Clean) and decide (Decide),
plus paper_stats aggregation. No indicators involved.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

import research_loop as rl


class CleanDatasetTest(unittest.TestCase):
    def _rows(self, root):
        os.makedirs(os.path.join(root, "nifty"), exist_ok=True)
        day = os.path.join(root, "nifty", "2026-08-18.jsonl")
        rows = [
            {"ts": "2026-08-18T10:00:00", "asset": "nifty", "spot": 24200.0,
             "expiry": "2026-08-25", "strike": 24000, "ce_ltp": 100.0, "pe_ltp": 50.0,
             "ce_bid": 99.5, "ce_ask": 100.5, "pe_bid": 49.5, "pe_ask": 50.5},
            {"ts": "2026-08-18T10:00:00", "asset": "nifty", "spot": 24200.0,
             "expiry": "2026-08-25", "strike": 24000, "ce_ltp": 100.0, "pe_ltp": 50.0,
             "ce_bid": 99.5, "ce_ask": 100.5, "pe_bid": 49.5, "pe_ask": 50.5},
            {"ts": "2026-08-18T10:01:00", "asset": "nifty", "spot": 24200.0,
             "expiry": "2026-08-25", "strike": "xyz", "ce_ltp": 100.0},
            {"ts": "2026-08-18T10:01:00", "asset": "nifty", "spot": 24200.0,
             "expiry": "2026-08-25", "strike": 24100, "ce_ltp": None, "pe_ltp": None},
            {"ts": "2026-08-18T10:02:00", "asset": "nifty", "spot": 24200.0,
             "expiry": "2026-08-18", "strike": 24200, "ce_ltp": 100.0, "pe_ltp": 50.0},
        ]
        with open(day, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return day

    def test_cleaning_report_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._rows(tmp)
            df, rep = rl.clean_dataset("nifty", root=tmp)
        self.assertEqual(rep["raw"], 5)
        self.assertEqual(rep["parsed"], 5)
        self.assertEqual(rep["no_ts_or_strike"], 1)   # "xyz" strike
        self.assertEqual(rep["no_quote"], 1)           # no LTP either side
        self.assertEqual(rep["non_dominant_expiry"], 1)  # 18-Aug vs 25-Aug
        self.assertEqual(rep["duplicates"], 1)         # (10:00, 24000) twice
        self.assertEqual(rep["final"], 1)
        self.assertEqual(rep["days"], 1)
        self.assertEqual(rep["expiry"], "2026-08-25")

    def test_empty_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            df, rep = rl.clean_dataset("nifty", root=tmp)
        self.assertIsNone(df)
        self.assertEqual(rep["final"], 0)
        self.assertEqual(rep["files"], 0)

    def test_specified_expiry_keeps_that_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._rows(tmp)
            df, rep = rl.clean_dataset("nifty", root=tmp, expiry="2026-08-18")
        # only the 18-Aug row survives (its strike is 24200)
        self.assertEqual(rep["final"], 1)
        self.assertEqual(rep["expiry"], "2026-08-18")
        self.assertEqual(df.iloc[0]["strike"], 24200)


class DecideTest(unittest.TestCase):
    def _oos(self, n, ev, wr=0.5, pf=1.0):
        return {"n": n, "ev": ev, "wr": wr, "pf": pf, "net": ev * n if ev else 0.0}

    def test_too_few_days_keep_collecting(self):
        r = rl.decide({"days": 2}, self._oos(100, 5.0), {"n": 100, "net_rs": 500.0})
        self.assertEqual(r["stage"], "KEEP_COLLECTING")

    def test_too_few_oos_trades_keep_collecting(self):
        r = rl.decide({"days": 10}, self._oos(10, 5.0), {"n": 100, "net_rs": 500.0})
        self.assertEqual(r["stage"], "KEEP_COLLECTING")

    def test_negative_oos_edge_no_edge(self):
        r = rl.decide({"days": 10}, self._oos(30, -4.0), {"n": 30, "net_rs": 100.0})
        self.assertEqual(r["stage"], "NO_EDGE_OOS")

    def test_positive_oos_insufficient_paper_paper_trade(self):
        r = rl.decide({"days": 10}, self._oos(30, 8.0), {"n": 5, "net_rs": 40.0})
        self.assertEqual(r["stage"], "PAPER_TRADE")

    def test_live_matches_backtest_edge_confirmed(self):
        # oos_ev 8, paper_ev 8 (net_rs 240 / n 30) → gap 0
        r = rl.decide({"days": 10}, self._oos(30, 8.0), {"n": 30, "net_rs": 240.0})
        self.assertEqual(r["stage"], "EDGE_CONFIRMED")
        self.assertLessEqual(r["gap"], rl.DRIFT_TOL)

    def test_live_diverges_drift(self):
        # oos_ev 8, paper_ev -8 → gap 2.0 > tolerance
        r = rl.decide({"days": 10}, self._oos(30, 8.0), {"n": 30, "net_rs": -240.0})
        self.assertEqual(r["stage"], "DRIFT")
        self.assertGreater(r["gap"], rl.DRIFT_TOL)


class PaperStatsTest(unittest.TestCase):
    def test_aggregates_daily_snapshots(self):
        hist = [
            {"date": "2026-08-14", "resolved": 20, "wins": 8, "net_rs": 100.0, "net_pts": 5.0},
            {"date": "2026-08-15", "resolved": 10, "wins": 5, "net_rs": -50.0, "net_pts": -2.0},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(hist, f)
            path = f.name
        try:
            with mock.patch.object(rl, "SCALP_PNL_HISTORY", path):
                s = rl.paper_stats()
        finally:
            os.unlink(path)
        self.assertEqual(s["days"], 2)
        self.assertEqual(s["n"], 30)
        self.assertEqual(s["wins"], 13)
        self.assertAlmostEqual(s["wr"], 13 / 30)
        self.assertAlmostEqual(s["net_rs"], 50.0)

    def test_missing_file_zeros(self):
        with mock.patch.object(rl, "SCALP_PNL_HISTORY", "/nonexistent/x.json"):
            s = rl.paper_stats()
        self.assertEqual(s["n"], 0)
        self.assertEqual(s["net_rs"], 0.0)


if __name__ == "__main__":
    unittest.main()
