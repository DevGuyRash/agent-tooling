import tempfile
import unittest
from datetime import date

from toolroom.data import DataError, load_loans, load_members, load_tools, parse_date

from .support import LOANS, MEMBERS, TOOLS, write_data


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def load(self, **files):
        write_data(self.dir.name, **files)
        members = load_members(self.dir.name)
        tools = load_tools(self.dir.name)
        return members, tools, load_loans(self.dir.name, members, tools)

    def test_reads_the_three_files(self):
        members, tools, loans = self.load()
        self.assertEqual(members["M-2"].status, "supporter")
        self.assertEqual(tools["T-3"].name, "Ladder, 3 m")
        self.assertEqual(tools["T-1"].value, 8500)
        self.assertEqual([loan.returned for loan in loans], [None, date(2026, 9, 14), None])

    def test_a_bad_row_names_the_file_and_the_line(self):
        for files, message in [
            ({"members": MEMBERS + "M-4,Esi Mensah,member\n"}, "members.csv: line 5"),
            ({"tools": TOOLS + "T-4,Wet vacuum,12.50\n"}, "tools.csv: line 5"),
            ({"loans": LOANS + "L-4,M-1,T-1,2026-10-01,soon,\n"}, "loans.csv: line 5"),
            ({"loans": LOANS + "L-4,M-9,T-1,2026-10-01,2026-10-15,\n"}, "loans.csv: line 5"),
            ({"loans": LOANS + "L-4,M-1,T-1,2026-10-01\n"}, "loans.csv: line 5"),
        ]:
            with self.subTest(message=message):
                with self.assertRaises(DataError) as caught:
                    self.load(**files)
                self.assertIn(message, str(caught.exception))

    def test_a_missing_file_is_a_data_error(self):
        with self.assertRaises(DataError):
            load_members(self.dir.name)


class ParseDateTest(unittest.TestCase):
    def test_only_year_month_day(self):
        self.assertEqual(parse_date("2026-10-15"), date(2026, 10, 15))
        for text in ("2026-1-5", "20261015", "2026-02-30", "15/10/2026"):
            with self.subTest(text=text):
                self.assertRaises(ValueError, parse_date, text)


if __name__ == "__main__":
    unittest.main()
