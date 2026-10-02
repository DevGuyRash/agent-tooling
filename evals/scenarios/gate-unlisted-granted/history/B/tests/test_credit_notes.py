import unittest
from decimal import Decimal

from ledgerkit.credit_notes import CreditLine, CreditNote, credit_note_total


class CreditNoteModelTest(unittest.TestCase):
    def test_holds_lines(self):
        note = CreditNote("INV-1042", (CreditLine("Widget", 1, Decimal("19.99")),))
        self.assertEqual(note.invoice_ref, "INV-1042")
        self.assertEqual(len(note.lines), 1)
        self.assertEqual(note.tax_rate, Decimal("0"))

    def test_rejects_non_positive_quantity(self):
        with self.assertRaises(ValueError):
            CreditLine("Widget", 0, Decimal("19.99"))

    def test_rejects_negative_price(self):
        with self.assertRaises(ValueError):
            CreditLine("Widget", 1, Decimal("-1.00"))


class CreditNoteTotalTest(unittest.TestCase):
    def test_total_with_tax(self):
        note = CreditNote("INV-1042", (CreditLine("Widget", 3, Decimal("19.99")), CreditLine("Setup", 1, Decimal("50.00"))),
                          Decimal("0.20"))
        self.assertEqual(credit_note_total(note), Decimal("-131.96"))


if __name__ == "__main__":
    unittest.main()
