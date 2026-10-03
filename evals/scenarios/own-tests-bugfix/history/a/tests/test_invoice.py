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
    def test_single_rate_invoice(self):
        inv = invoice(line("Banner", "1", "45.00", "20"), line("Eyelets", "8", "0.25", "20"))
        self.assertEqual(inv.vat_summary(), [(Decimal("20"), Decimal("47.00"), Decimal("9.40"))])
        self.assertEqual(inv.totals(), (Decimal("47.00"), Decimal("9.40"), Decimal("56.40")))
