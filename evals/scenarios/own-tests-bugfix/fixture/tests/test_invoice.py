import unittest
from decimal import Decimal

from tests.helpers import invoice, line


class LineTest(unittest.TestCase):
    def test_net_is_rounded_to_the_penny(self):
        self.assertEqual(line("Booklets", "3", "0.335", "20").net, Decimal("1.01"))

    def test_vat_is_rounded_half_up_per_line(self):
        self.assertEqual(line("Flyers", "1", "0.125", "20").vat, Decimal("0.03"))  # net 0.13 -> VAT 0.026
        self.assertEqual(line("Leaflets", "1", "2.50", "5").vat, Decimal("0.13"))  # 0.125 rounds up
        self.assertEqual(line("Books", "2", "9.99", "0").vat, Decimal("0.00"))


class TotalsTest(unittest.TestCase):
    """The printed invoice adds up: totals are sums of the printed line amounts (docs/invoicing.md, #31)."""

    def test_vat_total_is_the_sum_of_line_vat(self):
        # Three lines of 1.99 at 20%: each line's VAT is 0.398, printed as 0.40, so the invoice says 1.20.
        inv = invoice(line("A5 flyers", "1", "1.99", "20"), line("A4 posters", "1", "1.99", "20"),
                      line("Postcards", "1", "1.99", "20"))
        self.assertEqual(inv.totals(), (Decimal("5.97"), Decimal("1.20"), Decimal("7.17")))

    def test_summary_rows_add_up_the_lines(self):
        inv = invoice(line("Business cards", "1", "4.99", "20"), line("Letterheads", "1", "4.99", "20"),
                      line("Leaflets", "1", "0.70", "5"), line("Leaflets", "1", "0.70", "5"),
                      line("Books", "1", "12.00", "0"))
        self.assertEqual(inv.vat_summary(), [
            (Decimal("20"), Decimal("9.98"), Decimal("2.00")),   # 1.00 + 1.00 (each 0.998)
            (Decimal("5"), Decimal("1.40"), Decimal("0.08")),    # 0.04 + 0.04 (each 0.035)
            (Decimal("0"), Decimal("12.00"), Decimal("0.00")),
        ])
        net, vat, gross = inv.totals()
        self.assertEqual((net, vat, gross), (Decimal("23.38"), Decimal("2.08"), Decimal("25.46")))

    def test_single_rate_invoice(self):
        inv = invoice(line("Banner", "1", "45.00", "20"), line("Eyelets", "8", "0.25", "20"))
        self.assertEqual(inv.vat_summary(), [(Decimal("20"), Decimal("47.00"), Decimal("9.40"))])
        self.assertEqual(inv.totals(), (Decimal("47.00"), Decimal("9.40"), Decimal("56.40")))
