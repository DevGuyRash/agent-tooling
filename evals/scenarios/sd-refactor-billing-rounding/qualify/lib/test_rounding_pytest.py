"""Characterization of how invoices round today (pytest style), green on the pre-extraction code.

These pin current behavior before the extraction; they are not tests written to fail first.
"""
import tempfile
from datetime import date
from decimal import Decimal as D

from billing.invoice import generate_invoice
from billing.models import Customer, LineItem, Order
from billing.store import InvoiceStore


def _invoice(region, tier, *lines):
    with tempfile.TemporaryDirectory() as tmp:
        customer = Customer("C-901", "Pinned Co", region, tier)
        return generate_invoice(Order("SO-901", customer, list(lines)), InvoiceStore(tmp), date(2026, 9, 1))


def test_line_amounts_round_half_cents_to_even():
    inv = _invoice("OR", "standard",
                   LineItem("FLD-MAN", "Manila folders, each", D("1"), D("0.125")),
                   LineItem("FLD-MAN", "Manila folders, each", D("3"), D("0.125")))
    assert [line.amount for line in inv.lines] == [D("0.12"), D("0.38")]
    assert inv.total == D("0.50")


def test_discount_and_tax_round_half_cents_to_even():
    discounted = _invoice("OR", "silver", LineItem("SVC-DLV", "Local delivery", D("1"), D("12.50"), taxable=False))
    assert (discounted.discount, discounted.total) == (D("0.62"), D("11.88"))
    taxed = _invoice("TX", "standard", LineItem("PAP-LTR", "Copy paper", D("2"), D("5.00")))
    assert (taxed.tax, taxed.total) == (D("0.82"), D("10.82"))


def test_tax_comes_from_the_unrounded_discounted_amount():
    inv = _invoice("CA", "gold", LineItem("PEN-GEL", "Gel pens, black, 12-pack", D("5"), D("8.75")))
    assert (inv.discount, inv.tax, inv.total) == (D("4.38"), D("2.85"), D("42.22"))


def test_subtotal_adds_up_the_printed_amounts(store):
    # `store` comes from the root conftest.py
    customer = Customer("C-902", "Fixture Co", "OR", "standard")
    lines = [LineItem("CUP-8", "Paper cups, 8 oz, each", D("150"), D("0.0325")),
             LineItem("FLD-MAN", "Manila folders, each", D("7"), D("0.125"))]
    inv = generate_invoice(Order("SO-902", customer, lines), store, date(2026, 9, 1))
    assert inv.subtotal == D("5.76")
