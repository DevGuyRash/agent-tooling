import unittest

from helpers import ts
from meterwatch.events import Event
from meterwatch.rollup import daily_totals, top_keys, utc_day


class DailyTotalsTest(unittest.TestCase):
    def test_events_split_at_utc_midnight(self):
        events = [Event(ts("2026-03-01 23:59"), "acme", 4), Event(ts("2026-03-02 00:01"), "acme", 6)]
        self.assertEqual(daily_totals(events), {"2026-03-01": {"acme": 4}, "2026-03-02": {"acme": 6}})

    def test_a_days_events_are_summed_per_key(self):
        events = [
            Event(ts("2026-03-01 00:30"), "acme", 4),
            Event(ts("2026-03-01 12:00"), "acme", 3),
            Event(ts("2026-03-01 23:30"), "beta", 2),
            Event(ts("2026-03-01 23:45"), "acme", 1),
        ]
        self.assertEqual(daily_totals(events), {"2026-03-01": {"acme": 8, "beta": 2}})

    def test_the_epoch_is_a_utc_day(self):
        self.assertEqual(utc_day(0), "1970-01-01")


class KeyFilterTest(unittest.TestCase):
    def test_only_the_wanted_key_is_counted(self):
        events = [Event(1772325000, "acme", 4), Event(1772325100, "beta", 5), Event(1772325200, "acme", 1)]
        self.assertEqual(daily_totals(events, key="acme"), {"2026-03-01": {"acme": 5}})


class TopKeysTest(unittest.TestCase):
    def test_busiest_first_and_ties_by_key(self):
        events = [Event(1, "beta", 5), Event(2, "acme", 5), Event(3, "gamma", 9)]
        self.assertEqual(top_keys(events), [("gamma", 9), ("acme", 5), ("beta", 5)])

    def test_n_limits_the_list(self):
        events = [Event(1, "beta", 5), Event(2, "acme", 6), Event(3, "gamma", 9)]
        self.assertEqual(top_keys(events, n=2), [("gamma", 9), ("acme", 6)])


class SinceTest(unittest.TestCase):
    def test_earlier_days_are_dropped(self):
        events = [Event(ts("2026-03-01 12:00"), "acme", 4), Event(ts("2026-03-02 12:00"), "acme", 6)]
        self.assertEqual(daily_totals(events, since="2026-03-02"), {"2026-03-02": {"acme": 6}})
