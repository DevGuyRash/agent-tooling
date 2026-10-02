import unittest
from pathlib import Path

from circdesk.loans import ExportError, read_loans
from circdesk.receipt import receipt

LOANS = read_loans(Path(__file__).parent / "data" / "loans.csv")


class ReceiptTest(unittest.TestCase):
    def test_adult_book_six_days_late(self):
        self.assertEqual(receipt(LOANS, "L-30112"),
                         "Returned: The Salt Path (31207000418823)\n"
                         "Due 2026-09-14, returned 2026-09-20: 6 days late\n"
                         "Fine: 1.80\n")

    def test_one_day_late_is_within_grace(self):
        self.assertEqual(receipt(LOANS, "L-30115"),
                         "Returned: Paddington at the Zoo (31207000533109)\n"
                         "Due 2026-09-14, returned 2026-09-15: 1 day late\n"
                         "Fine: none\n")

    def test_dvd(self):
        self.assertTrue(receipt(LOANS, "L-30120").endswith("4 days late\nFine: 5.00\n"))
        self.assertTrue(receipt(LOANS, "L-30126").endswith("8 days late\nFine: 10.00\n"))

    def test_on_time(self):
        self.assertTrue(receipt(LOANS, "L-30144").endswith(": on time\nFine: none\n"))

    def test_not_returned(self):
        with self.assertRaisesRegex(ExportError, "not been returned"):
            receipt(LOANS, "L-30131")


if __name__ == "__main__":
    unittest.main()
