import json
import unittest

from stampcard.batch import run
from stampcard.directory import Card, Directory

CARDS = {"C-001": Card("C-001", "Ada", 8), "C-004": Card("C-004", "Di", 0)}


def line(event_id, card, kind, cents):
    return json.dumps({"id": event_id, "card": card, "kind": kind, "cents": cents, "ts": "2026-10-01T09:02:00"})


class RunTest(unittest.TestCase):
    def test_counts_and_cards(self):
        sent = []
        lines = [line("e1", "C-001", "purchase", 450), "", "oops", line("e2", "C-004", "purchase", 900)]
        summary = run(lines, Directory(CARDS.get), sent.append)
        self.assertEqual((summary.events, summary.applied, summary.rejected), (3, 2, {"malformed": 1}))
        self.assertEqual(summary.cards, [("C-001", 9, 0), ("C-004", 2, 0)])
        self.assertEqual(sent, [])

    def test_a_free_drink_notifies_the_customer(self):
        sent = []
        summary = run([line("e1", "C-001", "purchase", 800)], Directory(CARDS.get), sent.append)
        self.assertEqual((summary.drinks, summary.notify_failed), (1, 0))
        self.assertEqual([m["to"] for m in sent], ["C-001"])


if __name__ == "__main__":
    unittest.main()
