import unittest
from decimal import Decimal

from ledgerkit.invoices import Invoice, Line, invoice_total
from ledgerkit.money import round_money


class InvoiceTotalTest(unittest.TestCase):
    def test_total_with_tax(self):
        inv = Invoice("INV-1042", (Line("Widget", 3, Decimal("19.99")), Line("Setup", 1, Decimal("50.00"))), Decimal("0.20"))
        self.assertEqual(invoice_total(inv), Decimal("131.96"))

    def test_no_lines(self):
        self.assertEqual(invoice_total(Invoice("INV-1043", ())), Decimal("0.00"))

    def test_halves_round_up(self):
        self.assertEqual(invoice_total(Invoice("INV-1044", (Line("Part", 1, Decimal("0.125")),))), Decimal("0.13"))


class RoundMoneyTest(unittest.TestCase):
    def test_halves_away_from_zero(self):
        self.assertEqual(round_money(Decimal("2.345")), Decimal("2.35"))
        self.assertEqual(round_money(Decimal("-2.345")), Decimal("-2.35"))


if __name__ == "__main__":
    unittest.main()
