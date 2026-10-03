import datetime
import os
import tempfile
import unittest

from loanbook.records import RecordsError, load, read_loans


class RecordsTests(unittest.TestCase):
    def test_loads_the_sample_data(self):
        library = load("data")
        self.assertEqual(library.items["H-12"].name, "Hedge trimmer")
        self.assertEqual(library.members["M014"].phone, "07700 900314")
        self.assertEqual(len(library.loans), 11)
        first = library.loans[0]
        self.assertEqual((first.loan, first.due, first.returned), ("L0288", datetime.date(2026, 9, 30), None))
        self.assertTrue(first.open)

    def test_bad_date_names_the_line(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write("loan,item,member,out,due,returned\nL1,D-01,M003,2026-09-01,2026-9-8,\n")
        try:
            with self.assertRaisesRegex(RecordsError, "line 2: bad date '2026-9-8'"):
                read_loans(path)
        finally:
            os.unlink(path)

    def test_wrong_columns(self):
        with self.assertRaisesRegex(RecordsError, "expected columns"):
            read_loans("data/items.csv")


if __name__ == "__main__":
    unittest.main()
