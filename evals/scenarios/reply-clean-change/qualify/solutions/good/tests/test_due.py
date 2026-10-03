import datetime
import unittest

from loanbook.records import load
from loanbook.report import due_lines


class DueTests(unittest.TestCase):
    def setUp(self):
        self.library = load("data")

    def test_docs_example(self):
        lines = due_lines(self.library, datetime.date(2026, 10, 5), 2)
        self.assertEqual(lines[0], "Due 2026-10-05 to 2026-10-07")
        self.assertEqual(lines[2:4], ["Priya Shah (07700 900314)", "  2026-10-05  Hedge trimmer (H-12)"])
        self.assertEqual(lines[-1], "4 loans, 3 members")

    def test_returned_and_overdue_loans_are_left_out(self):
        text = "\n".join(due_lines(self.library, datetime.date(2026, 10, 4), 3))
        self.assertNotIn("Hammer drill", text)  # returned
        self.assertNotIn("Tile cutter", text)  # overdue
        self.assertIn("Gazebo", text)  # due on the first day

    def test_last_day_is_included(self):
        lines = due_lines(self.library, datetime.date(2026, 10, 7), 1)
        self.assertIn("  2026-10-08  Wallpaper steamer (W-03)", lines)

    def test_nothing_due(self):
        self.assertEqual(due_lines(self.library, datetime.date(2026, 11, 1), 2),
                         ["Nothing due 2026-11-01 to 2026-11-03"])


if __name__ == "__main__":
    unittest.main()
