import tempfile
import unittest
from pathlib import Path

from deskd import store


class LoadTest(unittest.TestCase):
    def write(self, text):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / "t.jsonl"
        p.write_text(text, encoding="utf-8")
        return p

    def test_sorted_by_id(self):
        tickets = store.load(Path(__file__).parent / "data" / "tickets.jsonl")
        self.assertEqual([t.id for t in tickets], [4101, 4177, 4182, 4190, 4195])

    def test_not_json(self):
        with self.assertRaisesRegex(store.StoreError, "line 1: not JSON"):
            store.load(self.write("{oops\n"))

    def test_duplicate(self):
        line = '{"id": 1, "subject": "s", "customer": "c", "priority": "P1", "status": "open", "opened_at": "2026-10-01T09:00"}\n'
        with self.assertRaisesRegex(store.StoreError, "line 2: ticket 1 appears twice"):
            store.load(self.write(line + line))

    def test_bad_time(self):
        line = '{"id": 1, "subject": "s", "customer": "c", "priority": "P1", "status": "open", "opened_at": "2026-10-01 09:00"}\n'
        with self.assertRaisesRegex(store.StoreError, "opened_at must look like"):
            store.load(self.write(line))


if __name__ == "__main__":
    unittest.main()
