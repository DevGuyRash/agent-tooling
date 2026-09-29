"""Characterization by oracle: a frozen copy of the invoice calculation as it stood before pricing moved
out of generate_invoice. Invoices must keep matching it on orders full of half cents. Green on the code
as it was; it guards the extraction rather than specifying anything new.
"""
import itertools
import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

from billing.invoice import generate_invoice
from billing.models import Customer, LineItem, Order
from billing.rates import TAX_RATES, TIER_DISCOUNTS
from billing.store import InvoiceStore


def legacy_totals(lines, customer):
    # Copied from generate_invoice before the extraction; do not "fix" this.
    amounts = [D(f"{line.unit_price * line.quantity:.2f}") for line in lines]
    subtotal = sum(amounts, D("0.00"))
    taxable = sum((a for a, line in zip(amounts, lines) if line.taxable), D("0.00"))
    rate = TIER_DISCOUNTS[customer.tier]
    discount = D(f"{subtotal * rate:.2f}")
    tax = D(f"{taxable * (1 - rate) * TAX_RATES[customer.region]:.2f}")
    return amounts, subtotal, discount, tax, subtotal - discount + tax


PRICES = ["0.125", "0.875", "0.0325", "2.35", "12.50", "22.45"]
QUANTITIES = ["1", "3", "5", "7", "1.5"]


class LegacyEquivalenceTest(unittest.TestCase):
    def test_invoices_match_the_legacy_calculation(self):
        for region, tier in itertools.product(sorted(TAX_RATES), sorted(TIER_DISCOUNTS)):
            customer = Customer("C-1", "Oracle Co", region, tier)
            for i, (p1, p2) in enumerate(itertools.combinations(PRICES, 2)):
                q1, q2 = QUANTITIES[i % 5], QUANTITIES[(i + 2) % 5]
                lines = [LineItem("A-1", "Item one", D(q1), D(p1)),
                         LineItem("B-2", "Item two", D(q2), D(p2), taxable=i % 3 != 0)]
                with self.subTest(region=region, tier=tier, lines=(q1, p1, q2, p2)):
                    with tempfile.TemporaryDirectory() as tmp:
                        inv = generate_invoice(Order("SO-1", customer, lines), InvoiceStore(tmp), date(2026, 9, 1))
                    amounts, subtotal, discount, tax, total = legacy_totals(lines, customer)
                    self.assertEqual([line.amount for line in inv.lines], amounts)
                    self.assertEqual((inv.subtotal, inv.discount, inv.tax, inv.total), (subtotal, discount, tax, total))


if __name__ == "__main__":
    unittest.main()
