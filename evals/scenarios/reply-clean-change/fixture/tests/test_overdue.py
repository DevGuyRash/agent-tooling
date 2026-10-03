import datetime
import unittest

from loanbook.records import load
from loanbook.report import overdue_lines


class OverdueTests(unittest.TestCase):
    def setUp(self):
        self.library = load("data")

    def test_grouped_by_member_most_overdue_first(self):
        lines = overdue_lines(self.library, datetime.date(2026, 10, 5))
        self.assertEqual(lines[0], "Overdue on 2026-10-05")
        self.assertEqual(lines[2], "Tom Okoro (07700 900322)")
        self.assertEqual(lines[3], "  2026-09-30  Cordless drill (D-01), 5 days late")
        self.assertEqual(lines[-1], "3 loans, 2 members")

    def test_returned_loans_are_not_overdue(self):
        lines = overdue_lines(self.library, datetime.date(2026, 10, 6))
        self.assertFalse(any("Sewing machine" in l or "Hammer drill" in l for l in lines))

    def test_nothing_overdue(self):
        self.assertEqual(overdue_lines(self.library, datetime.date(2026, 9, 1)), ["Nothing overdue on 2026-09-01"])


if __name__ == "__main__":
    unittest.main()
