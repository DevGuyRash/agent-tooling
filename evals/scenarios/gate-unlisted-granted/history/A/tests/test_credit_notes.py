import unittest
from decimal import Decimal

from ledgerkit.credit_notes import CreditLine, CreditNote


class CreditNoteModelTest(unittest.TestCase):
    def test_holds_lines(self):
        note = CreditNote("INV-1042", (CreditLine("Widget", 1, Decimal("19.99")),))
        self.assertEqual(note.invoice_ref, "INV-1042")
        self.assertEqual(len(note.lines), 1)
        self.assertEqual(note.tax_rate, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
