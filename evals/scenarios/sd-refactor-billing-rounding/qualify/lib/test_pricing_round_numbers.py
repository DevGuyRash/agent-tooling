import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

from billing.invoice import generate_invoice
from billing.models import Customer, LineItem, Order
from billing.pricing import price_order
from billing.store import InvoiceStore

TEXAN = Customer("C-100", "Lone Star Dental", "TX")
GOLD = Customer("C-200", "Harbor Law LLP", "TX", tier="gold")
PAPER = LineItem("PAP-LTR", "Copy paper, letter, 500 sheets", D("4"), D("5.00"))
TONER = LineItem("TON-12", "Toner cartridge, black", D("1"), D("20.00"))
SETUP = LineItem("SVC-SETUP", "Printer setup (service)", D("1"), D("15.00"), taxable=False)


class PriceOrderTest(unittest.TestCase):
    def test_totals(self):
        price = price_order([PAPER, TONER], TEXAN)
        self.assertEqual([line.amount for line in price.lines], [D("20.00"), D("20.00")])
        self.assertEqual((price.subtotal, price.discount, price.tax, price.total),
                         (D("40.00"), D("0.00"), D("3.30"), D("43.30")))

    def test_discount_and_untaxed_line(self):
        price = price_order([PAPER, TONER, SETUP], GOLD)
        self.assertEqual((price.subtotal, price.discount, price.tax, price.total),
                         (D("55.00"), D("5.50"), D("2.97"), D("52.47")))

    def test_matches_the_invoice(self):
        with tempfile.TemporaryDirectory() as tmp:
            inv = generate_invoice(Order("SO-1", GOLD, [PAPER, TONER, SETUP]), InvoiceStore(tmp), date(2026, 9, 1))
        price = price_order([PAPER, TONER, SETUP], GOLD)
        self.assertEqual((price.subtotal, price.discount, price.tax, price.total),
                         (inv.subtotal, inv.discount, inv.tax, inv.total))

    def test_rejects_an_empty_order(self):
        with self.assertRaises(ValueError):
            price_order([], TEXAN)


if __name__ == "__main__":
    unittest.main()
