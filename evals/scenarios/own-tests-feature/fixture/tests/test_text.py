import unittest

from shiftboard.text import table


class TableTest(unittest.TestCase):
    def test_columns_line_up_under_a_rule(self):
        lines = table(["Name", "Hours"], [("Amara Okafor", "6.0"), ("Ines Duarte", "12.5")])
        self.assertEqual(lines, [
            "Name          Hours",
            "------------  -----",
            "Amara Okafor  6.0",
            "Ines Duarte   12.5",
        ])

    def test_no_trailing_spaces(self):
        lines = table(["A", "Long header"], [("x", "")])
        self.assertTrue(all(line == line.rstrip() for line in lines))
        self.assertEqual(lines[2], "x")
