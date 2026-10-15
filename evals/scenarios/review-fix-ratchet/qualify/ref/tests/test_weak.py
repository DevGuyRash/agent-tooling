import json
import unittest

from stampcard.batch import run
from stampcard.directory import Card, Directory

CARDS = {"C-001": Card("C-001", "Ada", 8), "C-002": Card("C-002", "Ben", 9)}


def line(n, card, kind, cents):
    return json.dumps({"id": "e%d" % n, "card": card, "kind": kind, "cents": cents, "ts": "2026-10-01T09:0%d:00" % n})


class ReviewFollowUpTest(unittest.TestCase):
    def test_exactly_ten_stamps_earn_a_drink(self):
        summary = run([line(1, "C-002", "purchase", 400)], Directory(CARDS.get), lambda message: None)
        self.assertEqual((summary.drinks, summary.cards), (1, [("C-002", 0, 1)]))

    def test_a_refund_that_leaves_stamps_on_the_card(self):
        summary = run([line(1, "C-001", "refund", 800)], Directory(CARDS.get), lambda message: None)
        self.assertEqual(summary.cards, [("C-001", 6, 0)])

    def test_known_cards_are_applied(self):
        summary = run([line(1, "C-001", "purchase", 450)], Directory(CARDS.get), lambda message: None)
        self.assertEqual((summary.applied, summary.rejected), (1, {}))


if __name__ == "__main__":
    unittest.main()
