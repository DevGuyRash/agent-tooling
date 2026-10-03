import unittest

from shiftboard.board import render_week
from shiftboard.text import table


class WideTableTest(unittest.TestCase):
    def test_wide_names_line_up(self):
        lines = table(["Day", "Volunteer", "Station"], [("Mon 14", "张伟", "Prep"), ("Mon 14", "Amara Okafor", "Serving")])
        self.assertEqual(lines, [
            "Day     Volunteer     Station",
            "------  ------------  -------",
            "Mon 14  张伟          Prep",
            "Mon 14  Amara Okafor  Serving",
        ])

    def test_bad_week_format(self):
        with self.assertRaises(ValueError):
            render_week([], "2026-38")
