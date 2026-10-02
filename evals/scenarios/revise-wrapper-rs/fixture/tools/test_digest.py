import contextlib
import io
import os
import tempfile
import unittest

import digest


class Tenths(unittest.TestCase):
    def test_round_trip(self):
        for text, t in [("-18.5", -185), ("3.0", 30), ("-0.4", -4), ("0.0", 0)]:
            self.assertEqual(digest.tenths(text), t)
            self.assertEqual(digest.degrees(t), text)


class Rows(unittest.TestCase):
    def test_figures(self):
        units = {"congélateur-1": {"2026-09-21": [("06:00", -190), ("06:30", -175), ("07:00", -177), ("07:30", -196)]}}
        ranges = {"congélateur-1": (-250, -180)}
        [row] = digest.rows(units, ranges)
        # mean -184.5 and median -183.5 tenths: a half goes to the even tenth
        self.assertEqual(row, ["congélateur-1", "2026-09-21", "4", "-19.6", "-17.5", "-18.4", "-18.4", "2", "-17.5 at 06:30"])

    def test_first_of_equally_bad(self):
        units = {"frigo-lait": {"2026-09-21": [("06:00", 46), ("06:30", -6), ("07:00", 46)]}}
        [row] = digest.rows(units, {"frigo-lait": (0, 40)})
        self.assertEqual(row[7:], ["3", "4.6 at 06:00"])

    def test_unit_without_range(self):
        [row] = digest.rows({"frigo-cave": {"2026-09-21": [("06:00", 21)]}}, {})
        self.assertEqual(row[7:], ["-", "-"])

    def test_units_keep_their_order_days_are_sorted(self):
        units = {"frigo-lait": {"2026-09-22": [("06:00", 30)], "2026-09-21": [("06:00", 31)]},
                 "congélateur-1": {"2026-09-21": [("06:00", -190)]}}
        got = [(row[0], row[1]) for row in digest.rows(units, {})]
        self.assertEqual(got, [("frigo-lait", "2026-09-21"), ("frigo-lait", "2026-09-22"), ("congélateur-1", "2026-09-21")])


class Layout(unittest.TestCase):
    def test_columns(self):
        body = [["frigo-entrée", "2026-09-21", "48", "2.1", "5.2", "3.4", "3.3", "3", "5.2 at 14:30"]]
        self.assertEqual(digest.layout(body), [
            "unit          day          n  min  max  mean  median  out  worst",
            "frigo-entrée  2026-09-21  48  2.1  5.2   3.4     3.3    3  5.2 at 14:30",
        ])


class Main(unittest.TestCase):
    def test_no_readings_on_day(self):
        with tempfile.TemporaryDirectory() as d:
            units, log = os.path.join(d, "units.tsv"), os.path.join(d, "a.log")
            with open(units, "w", encoding="utf-8") as fh:
                fh.write("frigo-lait\t0.0\t4.0\n")
            with open(log, "w", encoding="utf-8") as fh:
                fh.write("2026-09-21T06:00Z\tfrigo-lait\t3.1\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(digest.main(["--units", units, "--day", "2026-09-22", log]), 0)
            self.assertEqual(out.getvalue(), "no readings on 2026-09-22\n")


if __name__ == "__main__":
    unittest.main()
