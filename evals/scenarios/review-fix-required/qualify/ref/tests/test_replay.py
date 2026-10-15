import json
import unittest

from stampcard.batch import run
from stampcard.directory import Card, Directory


class ReplayTest(unittest.TestCase):
    def test_an_event_applied_twice_is_rejected_as_a_replay(self):  # R3
        line = json.dumps({"id": "e1", "card": "C-004", "kind": "purchase", "cents": 450, "ts": "2026-10-01T09:01:00"})
        summary = run([line, line], Directory({"C-004": Card("C-004", "Di", 0)}.get), lambda message: None)
        self.assertEqual((summary.applied, summary.rejected, summary.cards), (1, {"replay": 1}, [("C-004", 1, 0)]))


if __name__ == "__main__":
    unittest.main()
