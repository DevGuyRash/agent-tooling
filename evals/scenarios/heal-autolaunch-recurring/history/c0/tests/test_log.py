import tempfile
import unittest
from datetime import date
from pathlib import Path

from chorelog.log import Entry, append_entry, parse_line, read_entries


class LogTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "chores.log"

    def test_parse_line(self):
        entry = parse_line("2026-09-14 mara take out the trash")
        self.assertEqual(entry, Entry(date(2026, 9, 14), "mara", "take out the trash"))

    def test_a_missing_file_has_no_entries(self):
        self.assertEqual(read_entries(self.path), [])

    def test_append_then_read(self):
        append_entry(self.path, Entry(date(2026, 9, 14), "mara", "dishes"))
        append_entry(self.path, Entry(date(2026, 9, 15), "ines", "laundry"))
        self.assertEqual([e.person for e in read_entries(self.path)], ["mara", "ines"])


if __name__ == "__main__":
    unittest.main()
