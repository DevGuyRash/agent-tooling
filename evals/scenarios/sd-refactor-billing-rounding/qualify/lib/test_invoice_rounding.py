"""Characterization tests: how invoices round today.

Written before pricing was pulled out of generate_invoice and green against the code as it was. They
record current behavior, including its half-to-even rounding, so the extraction can be checked against
it; they are not red-first tests for new behavior. The expected values come from running the
pre-extraction generate_invoice.
"""
import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

from billing.invoice import generate_invoice
from billing.models import Customer, LineItem, Order
from billing.store import InvoiceStore


class InvoiceRoundingCharacterizationTest(unittest.TestCase):
    def invoice(self, region, tier, *lines):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        customer = Customer("C-900", "Characterization Co", region, tier)
        return generate_invoice(Order("SO-900", customer, list(lines)), InvoiceStore(tmp.name), date(2026, 9, 1))

    def assertTotals(self, inv, subtotal, discount, tax, total):
        self.assertEqual((inv.subtotal, inv.discount, inv.tax, inv.total), (D(subtotal), D(discount), D(tax), D(total)))

    def test_line_amounts_round_half_cents_to_even(self):
        inv = self.invoice("OR", "standard",
                           LineItem("FLD-MAN", "Manila folders, each", D("1"), D("0.125")),
                           LineItem("FLD-MAN", "Manila folders, each", D("3"), D("0.125")))
        self.assertEqual([line.amount for line in inv.lines], [D("0.12"), D("0.38")])
        self.assertTotals(inv, "0.50", "0.00", "0.00", "0.50")

    def test_subtotal_adds_up_the_printed_line_amounts(self):
        inv = self.invoice("OR", "standard",
                           LineItem("CUP-8", "Paper cups, 8 oz, each", D("150"), D("0.0325")),
                           LineItem("FLD-MAN", "Manila folders, each", D("7"), D("0.125")))
        self.assertEqual([line.amount for line in inv.lines], [D("4.88"), D("0.88")])
        self.assertTotals(inv, "5.76", "0.00", "0.00", "5.76")  # not 5.75, the rounded sum of 4.875 + 0.875

    def test_discount_rounds_half_cents_to_even(self):
        inv = self.invoice("OR", "silver", LineItem("SVC-DLV", "Local delivery", D("1"), D("12.50"), taxable=False))
        self.assertTotals(inv, "12.50", "0.62", "0.00", "11.88")  # 5% of 12.50 is 0.625

    def test_tax_rounds_half_cents_to_even(self):
        inv = self.invoice("TX", "standard", LineItem("PAP-LTR", "Copy paper", D("2"), D("5.00")))
        self.assertTotals(inv, "10.00", "0.00", "0.82", "10.82")  # 8.25% of 10.00 is 0.825

    def test_tax_comes_from_the_unrounded_discounted_amount(self):
        inv = self.invoice("CA", "gold", LineItem("PEN-GEL", "Gel pens, black, 12-pack", D("5"), D("8.75")))
        self.assertTotals(inv, "43.75", "4.38", "2.85", "42.22")  # 7.25% of 39.375, not of 39.38

    def test_printed_amounts(self):
        inv = self.invoice("TX", "silver",
                           LineItem("CLP-100", "Paper clips, box of 100", D("3"), D("0.875")),
                           LineItem("INK-C", "Ink cartridge, cyan", D("1"), D("22.45")))
        lines = inv.text.splitlines()
        self.assertTrue(lines[7].startswith("CLP-100") and lines[7].endswith(" 2.62"), lines[7])
        self.assertEqual([line.split()[-1] for line in lines[-4:]], ["25.07", "-1.25", "1.96", "25.78"])


if __name__ == "__main__":
    unittest.main()
