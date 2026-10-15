import json
import unittest

from stampcard.batch import run
from stampcard.directory import Card, Directory
from stampcard.notify import notify_reward
from stampcard.report import render

CARDS = {"C-001": Card("C-001", "Ada", 8), "C-002": Card("C-002", "Ben", 9)}


def line(n, card, kind, cents):
    return json.dumps({"id": "e%d" % n, "card": card, "kind": kind, "cents": cents, "ts": "2026-10-01T09:0%d:00" % n})


def run_events(*events):
    return run(list(events), Directory(CARDS.get), lambda message: None)


class ReviewFollowUpTest(unittest.TestCase):
    def test_exactly_ten_stamps_earn_a_drink(self):
        self.assertEqual(run_events(line(1, "C-002", "purchase", 400)).cards, [("C-002", 0, 1)])

    def test_a_refund_that_leaves_stamps_on_the_card(self):
        self.assertEqual(run_events(line(1, "C-001", "refund", 800)).cards, [("C-001", 6, 0)])

    def test_known_cards_are_applied(self):
        self.assertEqual(run_events(line(1, "C-001", "purchase", 450)).applied, 1)

    def test_a_notification_that_works_is_sent_once(self):
        sent = []
        self.assertTrue(notify_reward(CARDS["C-001"], sent.append))
        self.assertEqual(len(sent), 1)

    def test_the_report_starts_with_its_title(self):
        self.assertTrue(render(run_events()).startswith("stampcard report\n"))

    def test_two_events_with_different_ids_are_both_applied(self):
        self.assertEqual(run_events(line(1, "C-001", "purchase", 450), line(2, "C-001", "purchase", 100)).applied, 2)


if __name__ == "__main__":
    unittest.main()
