import unittest
from decimal import Decimal

from meterwatch.invoice import build_invoice, line_amount

TOTALS = {
    "2026-03-01": {"acme": 10},
    "2026-03-02": {"acme": 20, "beta": 4},
    "2026-03-03": {"acme": 8},
}


class LineAmountTest(unittest.TestCase):
    def test_rounds_half_up_to_the_cent(self):
        self.assertEqual(line_amount(10, "0.0025"), Decimal("0.03"))
        self.assertEqual(line_amount(9, "0.0025"), Decimal("0.02"))

    def test_whole_cents_are_exact(self):
        self.assertEqual(line_amount(4, "0.25"), Decimal("1.00"))


class BuildInvoiceTest(unittest.TestCase):
    def test_every_day_is_priced_without_a_window(self):
        lines, total = build_invoice(TOTALS, "0.5")
        self.assertEqual(len(lines), 4)
        self.assertEqual(total, Decimal("21.00"))

    def test_the_first_day_is_included(self):
        lines, _ = build_invoice(TOTALS, "0.5", start="2026-03-02")
        self.assertEqual([line[0] for line in lines], ["2026-03-02", "2026-03-02", "2026-03-03"])

    def test_the_last_day_is_included(self):
        lines, total = build_invoice(TOTALS, "0.5", start="2026-03-01", end="2026-03-02")
        self.assertEqual([line[0] for line in lines], ["2026-03-01", "2026-03-02", "2026-03-02"])
        self.assertEqual(total, Decimal("17.00"))
