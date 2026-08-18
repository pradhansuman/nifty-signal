"""Offline tests: weekly expiry resolution (Tuesday → this week, else next Tuesday)."""
import datetime as _dt
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chain_table
import expiry_countdown


class _FakeDT(_dt.datetime):
    """A datetime subclass whose .now() returns a fixed instant."""
    _fixed = _dt.datetime(2026, 8, 18, 12, 0, 0)  # Tuesday

    @classmethod
    def now(cls, tz=None):
        return cls._fixed


class WeeklyExpiryTest(unittest.TestCase):
    def test_chain_next_tuesday_on_tuesday_returns_today(self):
        # On a Tuesday (weekly expiry day), the chain must show THIS week's expiry.
        with mock.patch.object(chain_table, "datetime", _FakeDT):
            self.assertEqual(chain_table._next_tuesday(), "2026-08-18")

    def test_chain_next_tuesday_on_monday_returns_tomorrow(self):
        _FakeDT._fixed = _dt.datetime(2026, 8, 17, 12, 0, 0)  # Monday
        with mock.patch.object(chain_table, "datetime", _FakeDT):
            self.assertEqual(chain_table._next_tuesday(), "2026-08-18")
        _FakeDT._fixed = _dt.datetime(2026, 8, 18, 12, 0, 0)  # restore

    def test_chain_next_tuesday_on_wednesday_returns_next_week(self):
        _FakeDT._fixed = _dt.datetime(2026, 8, 19, 12, 0, 0)  # Wednesday
        with mock.patch.object(chain_table, "datetime", _FakeDT):
            self.assertEqual(chain_table._next_tuesday(), "2026-08-25")
        _FakeDT._fixed = _dt.datetime(2026, 8, 18, 12, 0, 0)  # restore

    def test_expiry_countdown_weekly_on_tuesday_is_today(self):
        # _next_weekday(1) must return today (0 days) when today is Tuesday.
        with mock.patch.object(expiry_countdown, "datetime", _FakeDT):
            w = expiry_countdown._next_weekday(1)
            self.assertEqual((w.date() - _FakeDT.now().date()).days, 0)


if __name__ == "__main__":
    unittest.main()
