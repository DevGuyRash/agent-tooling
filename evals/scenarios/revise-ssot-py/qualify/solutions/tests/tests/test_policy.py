"""The 1 November 2026 policy (docs/fines.md) as each command charges it."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from circdesk.account import account
from circdesk.loans import read_loans, read_patrons
from circdesk.notices import notices
from circdesk.receipt import receipt

HEADER = "loan_id,patron_id,barcode,title,category,due,returned\n"
ROWS = [
    "L-1,P-1,301,Laptop 4,device,2026-11-01,2026-11-05",       # 4 days: 9.60
    "L-2,P-1,302,Laptop 8,device,2026-10-01,2026-11-05",       # 35 days: most 48.00
    "L-3,P-1,303,Coraline,children,2026-10-01,2026-10-25",     # 24 days: most 3.00
    "L-4,P-1,304,Dune,media,2026-11-01,2026-11-10",            # 9 days: 11.25
    "L-5,P-1,305,Emma,adult,2026-11-01,2026-11-04",            # 3 days: 1.05
    "L-6,P-2,306,Hotspot 2,device,2026-11-17,",                # 3 days out on 20 November: 7.20
]


class PolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.TemporaryDirectory()
        cls.addClassCleanup(d.cleanup)
        (Path(d.name) / "loans.csv").write_text(HEADER + "\n".join(ROWS) + "\n")
        (Path(d.name) / "patrons.csv").write_text("patron_id,name\nP-1,Ada Byrne\nP-2,Ben Ruiz\n")
        cls.loans = read_loans(Path(d.name) / "loans.csv")
        cls.patrons = read_patrons(Path(d.name) / "patrons.csv")

    def test_receipts(self):
        for loan_id, fine in [("L-1", "9.60"), ("L-2", "48.00"), ("L-3", "3.00"), ("L-4", "11.25"), ("L-5", "1.05")]:
            self.assertTrue(receipt(self.loans, loan_id).endswith(f"Fine: {fine}\n"), loan_id)

    def test_notice_from_the_third_day(self):
        self.assertIn("Hotspot 2 (306): due 2026-11-17, 3 days overdue, fine so far 7.20",
                      notices(self.loans, self.patrons, dt.date(2026, 11, 20)))

    def test_account(self):
        self.assertTrue(account(self.loans, self.patrons, "P-1", dt.date(2026, 11, 20)).endswith(
            "Total owed: 72.90\nBorrowing blocked until the total is under 10.00.\n"))


if __name__ == "__main__":
    unittest.main()
