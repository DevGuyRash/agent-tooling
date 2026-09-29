import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

from billing.invoice import generate_invoice
from billing.models import Customer, LineItem, Order
from billing.pricing import price_order
from billing.store import InvoiceStore

CUSTOMER = Customer("C-506", "Sonoma Vet Clinic", "CA", "gold")
LINES = [
    LineItem("SVC-DLV", "Local delivery", D("1"), D("12.50"), taxable=False),
    LineItem("INK-C", "Ink cartridge, cyan", D("3"), D("22.45")),
]


class PriceOrderTest(unittest.TestCase):
    def test_checkout_and_invoice_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            inv = generate_invoice(Order("SO-1", CUSTOMER, LINES), InvoiceStore(tmp), date(2026, 9, 1))
        price = price_order(LINES, CUSTOMER)
        self.assertEqual(price["lines"], [line.amount for line in inv.lines])
        self.assertEqual([price[k] for k in ("subtotal", "discount", "tax", "total")],
                         [inv.subtotal, inv.discount, inv.tax, inv.total])

    def test_pricing_does_not_use_an_invoice_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(tmp)
            price_order(LINES, CUSTOMER)
            self.assertEqual(store.next_number(), "INV-000001")

    def test_rejects_an_unknown_tier(self):
        with self.assertRaises(ValueError):
            price_order(LINES, Customer("C-7", "Someone", "CA", "platinum"))


if __name__ == "__main__":
    unittest.main()
