import datetime as dt
import unittest
from pathlib import Path

from circdesk.account import account
from circdesk.loans import read_loans, read_patrons

DATA = Path(__file__).parent / "data"
LOANS = read_loans(DATA / "loans.csv")
PATRONS = read_patrons(DATA / "patrons.csv")
DAY = dt.date(2026, 10, 6)


class AccountTest(unittest.TestCase):
    def test_returned_late(self):
        self.assertEqual(account(LOANS, PATRONS, "P-2041", DAY),
                         "Rosa Lindqvist (P-2041)\n"
                         "  The Salt Path (31207000418823): returned 6 days late, 1.80\n"
                         "Total owed: 1.80\n")

    def test_blocked_at_ten(self):
        self.assertEqual(account(LOANS, PATRONS, "P-2077", DAY),
                         "Kwame Mensah (P-2077)\n"
                         "  My Neighbour Totoro (31207001102952): returned 8 days late, 10.00\n"
                         "  Spirited Away (31207001102945): returned 4 days late, 5.00\n"
                         "  The Hobbit (31207000920017): out, 15 days overdue, 2.25\n"
                         "Total owed: 17.25\n"
                         "Borrowing blocked until the total is under 10.00.\n")

    def test_still_out(self):
        self.assertTrue(account(LOANS, PATRONS, "P-2103", DAY).endswith(
            "  Braiding Sweetgrass (31207000377640): out, 11 days overdue, 3.30\nTotal owed: 3.30\n"))


if __name__ == "__main__":
    unittest.main()
