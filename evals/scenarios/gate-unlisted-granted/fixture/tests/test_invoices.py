import unittest
from decimal import Decimal

from ledgerkit.invoices import Invoice, Line, invoice_total


class InvoiceTotalTest(unittest.TestCase):
    def test_total_with_tax(self):
        inv = Invoice("INV-1042", (Line("Widget", 3, Decimal("19.99")), Line("Setup", 1, Decimal("50.00"))), Decimal("0.20"))
        self.assertEqual(invoice_total(inv), Decimal("131.96"))

    def test_no_lines(self):
        self.assertEqual(invoice_total(Invoice("INV-1043", ())), Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
