import json
import unittest

from stampcard.batch import run
from stampcard.directory import Card, Directory

CARDS = {"C-001": Card("C-001", "Ada", 8), "C-003": Card("C-003", "Cy", 1), "C-004": Card("C-004", "Di", 0)}


def line(n, card, kind, cents):
    return json.dumps({"id": "e%d" % n, "card": card, "kind": kind, "cents": cents, "ts": "2026-10-01T09:0%d:00" % n})


def run_events(*events):
    return run(list(events), Directory(CARDS.get), lambda message: None)


class ReviewFixesTest(unittest.TestCase):
    def test_stamps_beyond_ten_stay_on_the_card(self):  # R6
        summary = run_events(line(1, "C-001", "purchase", 1200))
        self.assertEqual((summary.drinks, summary.cards), (1, [("C-001", 1, 1)]))

    def test_a_refund_stops_at_zero_stamps(self):  # R7
        summary = run_events(line(1, "C-003", "refund", 1200))
        self.assertEqual((summary.applied, summary.cards), (1, [("C-003", 0, 0)]))

    def test_an_unknown_card_is_rejected_and_the_run_goes_on(self):  # R8
        summary = run_events(line(1, "C-999", "purchase", 900), line(2, "C-004", "purchase", 450))
        self.assertEqual((summary.rejected, summary.applied, summary.cards), ({"unknown-card": 1}, 1, [("C-004", 1, 0)]))


if __name__ == "__main__":
    unittest.main()
