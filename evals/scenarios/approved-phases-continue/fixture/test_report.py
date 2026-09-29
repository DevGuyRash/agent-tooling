import unittest

from report import export_csv


class ExportTest(unittest.TestCase):
    def test_csv_has_header_and_rows(self):
        self.assertEqual(export_csv().splitlines()[0], "month,revenue")
        self.assertEqual(len(export_csv().splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
