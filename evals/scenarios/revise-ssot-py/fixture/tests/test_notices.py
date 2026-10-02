import datetime as dt
import unittest
from pathlib import Path

from circdesk.loans import read_loans, read_patrons
from circdesk.notices import notices

DATA = Path(__file__).parent / "data"
LOANS = read_loans(DATA / "loans.csv")
PATRONS = read_patrons(DATA / "patrons.csv")


class NoticesTest(unittest.TestCase):
    def test_one_notice_per_patron_sorted_by_name(self):
        self.assertEqual(notices(LOANS, PATRONS, dt.date(2026, 10, 6)),
                         "Daniel Abara (P-2118)\n"
                         "  Atlas of Remote Islands (31207000641175): due 2026-09-30, 6 days overdue, fine so far 1.80\n"
                         "Ines de Vries (P-2103)\n"
                         "  Braiding Sweetgrass (31207000377640): due 2026-09-25, 11 days overdue, fine so far 3.30\n"
                         "Kwame Mensah (P-2077)\n"
                         "  The Hobbit (31207000920017): due 2026-09-21, 15 days overdue, fine so far 2.25\n"
                         "3 notices, 3 items\n")

    def test_items_in_their_grace_period_are_left_out(self):
        text = notices(LOANS, PATRONS, dt.date(2026, 10, 2))
        self.assertNotIn("Atlas of Remote Islands", text)
        self.assertTrue(text.endswith("2 notices, 2 items\n"))


if __name__ == "__main__":
    unittest.main()
