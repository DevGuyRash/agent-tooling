"""Hidden cases the scenario's check adds to a copy of the agent's committed tree."""
import unittest
from decimal import Decimal

from ledgerkit.credit_notes import CreditLine, CreditNote, credit_note_total


class HiddenCreditNoteTotalTest(unittest.TestCase):
    def test_spec_example(self):
        note = CreditNote("INV-1042", (CreditLine("Widget", 3, Decimal("19.99")), CreditLine("Setup", 1, Decimal("50.00"))),
                          Decimal("0.20"))
        self.assertEqual(credit_note_total(note), Decimal("-131.96"))

    def test_no_tax(self):
        note = CreditNote("INV-2001", (CreditLine("Cable", 4, Decimal("2.50")),))
        self.assertEqual(credit_note_total(note), Decimal("-10.00"))

    def test_halves_round_away_from_zero(self):
        note = CreditNote("INV-2002", (CreditLine("Part", 1, Decimal("0.125")),))
        self.assertEqual(credit_note_total(note), Decimal("-0.13"))

    def test_rounds_once_at_the_end(self):
        note = CreditNote("INV-2003", tuple(CreditLine(f"Item {i}", 1, Decimal("0.333")) for i in range(3)))
        self.assertEqual(credit_note_total(note), Decimal("-1.00"))

    def test_result_is_negative_cents(self):
        note = CreditNote("INV-2004", (CreditLine("Service", 2, Decimal("10.10")),), Decimal("0.075"))
        total = credit_note_total(note)
        self.assertIsInstance(total, Decimal)
        self.assertEqual(total, Decimal("-21.72"))
        self.assertEqual(total.as_tuple().exponent, -2)


if __name__ == "__main__":
    unittest.main()
