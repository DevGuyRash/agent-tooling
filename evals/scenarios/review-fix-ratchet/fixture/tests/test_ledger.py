import unittest

from stampcard.directory import Card
from stampcard.events import Event
from stampcard.ledger import Ledger


def event(kind, cents):
    return Event("e1", "C-001", kind, cents, "2026-10-01T09:02:00")


class LedgerTest(unittest.TestCase):
    def test_a_purchase_earns_stamps(self):
        ledger = Ledger()
        self.assertEqual(ledger.apply(Card("C-001", "Ada", 2), event("purchase", 800)), 0)
        self.assertEqual(ledger.snapshot(), [("C-001", 4, 0)])

    def test_the_tenth_stamp_earns_a_free_drink(self):
        ledger = Ledger()
        self.assertEqual(ledger.apply(Card("C-001", "Ada", 9), event("purchase", 400)), 1)
        self.assertEqual(ledger.snapshot(), [("C-001", 0, 1)])

    def test_a_refund_takes_stamps_off(self):
        ledger = Ledger()
        ledger.apply(Card("C-001", "Ada", 6), event("refund", 800))
        self.assertEqual(ledger.snapshot(), [("C-001", 4, 0)])


if __name__ == "__main__":
    unittest.main()
