import datetime as dt
import tempfile
import unittest
from pathlib import Path

from circdesk.loans import ExportError, days_late, read_loans, read_patrons

DATA = Path(__file__).parent / "data"


class ReadLoansTest(unittest.TestCase):
    def test_reads_every_loan(self):
        loans = read_loans(DATA / "loans.csv")
        self.assertEqual(len(loans), 8)
        first = loans[0]
        self.assertEqual(first.loan_id, "L-30112")
        self.assertEqual(first.category, "adult")
        self.assertEqual(first.due, dt.date(2026, 9, 14))
        self.assertEqual(first.returned, dt.date(2026, 9, 20))

    def test_loan_still_out_has_no_return_date(self):
        loans = {l.loan_id: l for l in read_loans(DATA / "loans.csv")}
        self.assertIsNone(loans["L-30131"].returned)

    def _write(self, text):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / "loans.csv"
        p.write_text(text)
        return p

    def test_category_is_lowercased_and_values_trimmed(self):
        p = self._write("loan_id,patron_id,barcode,title,category,due,returned\n"
                        "L-1, P-1 ,312,Up, Media ,2026-09-01, \n")
        (loan,) = read_loans(p)
        self.assertEqual((loan.patron_id, loan.category, loan.returned), ("P-1", "media", None))

    def test_missing_column(self):
        p = self._write("loan_id,patron_id,barcode,title,due,returned\n")
        with self.assertRaisesRegex(ExportError, "no category column"):
            read_loans(p)

    def test_bad_date(self):
        p = self._write("loan_id,patron_id,barcode,title,category,due,returned\nL-1,P-1,312,Up,adult,2026-9-1,\n")
        with self.assertRaisesRegex(ExportError, "L-1"):
            read_loans(p)

    def test_missing_file(self):
        with self.assertRaises(ExportError):
            read_loans(DATA / "nope.csv")


class ReadPatronsTest(unittest.TestCase):
    def test_by_id(self):
        patrons = read_patrons(DATA / "patrons.csv")
        self.assertEqual(patrons["P-2103"].name, "Ines de Vries")


class DaysLateTest(unittest.TestCase):
    def test_on_or_before_due_is_not_late(self):
        due = dt.date(2026, 9, 14)
        self.assertEqual(days_late(due, dt.date(2026, 9, 14)), 0)
        self.assertEqual(days_late(due, dt.date(2026, 9, 1)), 0)

    def test_counts_calendar_days(self):
        self.assertEqual(days_late(dt.date(2026, 2, 27), dt.date(2026, 3, 2)), 3)


if __name__ == "__main__":
    unittest.main()
