import unittest
from decimal import Decimal

from ledgerline.normalize import clean_description, parse_amount


class AmountTest(unittest.TestCase):
    def test_plain_and_signed(self):
        self.assertEqual(parse_amount("-42.10"), Decimal("-42.10"))
        self.assertEqual(parse_amount("2400.00"), Decimal("2400.00"))

    def test_currency_symbols_and_commas(self):
        self.assertEqual(parse_amount("$1,305.20"), Decimal("1305.20"))

    def test_parenthesized_negative(self):
        self.assertEqual(parse_amount("($2,410.50)"), Decimal("-2410.50"))

    def test_empty_is_zero(self):
        self.assertEqual(parse_amount(""), Decimal("0"))


class DescriptionTest(unittest.TestCase):
    def test_collapses_whitespace(self):
        self.assertEqual(clean_description("  TRADER JOE'S #552   PHOENIX AZ "), "TRADER JOE'S #552 PHOENIX AZ")


if __name__ == "__main__":
    unittest.main()
