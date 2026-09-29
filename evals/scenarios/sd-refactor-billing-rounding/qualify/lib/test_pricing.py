import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

from billing.invoice import generate_invoice
from billing.models import Customer, LineItem, Order
from billing.pricing import price_order
from billing.store import InvoiceStore

GOLD_CA = Customer("C-510", "Santa Cruz Surf School", "CA", "gold")
LINES = [
    LineItem("TON-12", "Toner cartridge, black", D("2"), D("64.99")),
    LineItem("SVC-DLV", "Local delivery", D("1"), D("12.50"), taxable=False),
    LineItem("FLD-MAN", "Manila folders, each", D("5"), D("0.125")),
]


class PriceOrderTest(unittest.TestCase):
    def test_breakdown(self):
        price = price_order(LINES, GOLD_CA)
        self.assertEqual([line.amount for line in price.lines], [D("129.98"), D("12.50"), D("0.62")])
        self.assertEqual((price.subtotal, price.discount, price.tax, price.total),
                         (D("143.10"), D("14.31"), D("8.52"), D("137.31")))

    def test_checkout_and_invoice_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            inv = generate_invoice(Order("SO-1", GOLD_CA, LINES), InvoiceStore(tmp), date(2026, 9, 1))
        price = price_order(LINES, GOLD_CA)
        self.assertEqual([line.amount for line in price.lines], [line.amount for line in inv.lines])
        self.assertEqual((price.subtotal, price.discount, price.tax, price.total),
                         (inv.subtotal, inv.discount, inv.tax, inv.total))

    def test_rejects_what_cannot_be_invoiced(self):
        with self.assertRaises(ValueError):
            price_order([], GOLD_CA)
        with self.assertRaises(ValueError):
            price_order([LineItem("PAP-LTR", "Copy paper", D("0"), D("5.00"))], GOLD_CA)
        with self.assertRaises(ValueError):
            price_order(LINES, Customer("C-9", "Nowhere Inc", "ZZ"))


if __name__ == "__main__":
    unittest.main()
