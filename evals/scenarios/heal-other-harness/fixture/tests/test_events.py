import tempfile
import unittest
from pathlib import Path

from meterwatch.events import Event, load_events, parse_line


class ParseLineTest(unittest.TestCase):
    def test_reads_the_three_fields(self):
        line = '{"ts": 1772325000, "key": "acme", "units": 4}'
        self.assertEqual(parse_line(line), Event(1772325000, "acme", 4))

    def test_numbers_may_arrive_as_text(self):
        self.assertEqual(parse_line('{"ts": "10", "key": "acme", "units": "2"}'), Event(10, "acme", 2))


class LoadEventsTest(unittest.TestCase):
    def write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        handle.write(text)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def test_blank_lines_are_skipped(self):
        path = self.write('{"ts": 1, "key": "a", "units": 1}\n\n{"ts": 2, "key": "a", "units": 2}\n')
        self.assertEqual([event.units for event in load_events(path)], [1, 2])

    def test_a_bad_line_names_its_number(self):
        path = self.write('{"ts": 1, "key": "a", "units": 1}\nnot json\n')
        with self.assertRaisesRegex(ValueError, ":2: bad event"):
            load_events(path)
