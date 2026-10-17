import unittest
from datetime import date

from chorelog.log import Entry
from chorelog.report import count_by_person


def entry(person, day=1):
    return Entry(date(2026, 9, day), person, "dishes")


class ReportTest(unittest.TestCase):
    def test_most_entries_first(self):
        entries = [entry("ines"), entry("mara"), entry("mara", 2)]
        self.assertEqual(count_by_person(entries), [("mara", 2), ("ines", 1)])

    def test_ties_are_in_name_order(self):
        entries = [entry("noor"), entry("ines"), entry("mara")]
        self.assertEqual([person for person, _ in count_by_person(entries)], ["ines", "mara", "noor"])

    def test_no_entries(self):
        self.assertEqual(count_by_person([]), [])


if __name__ == "__main__":
    unittest.main()
