import unittest
from decimal import Decimal

from shelftag.money import format_rappen, parse_price, round_half_up


class MoneyTest(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_rappen(490), "4.90")
        self.assertEqual(format_rappen(5), "0.05")
        self.assertEqual(format_rappen(12800), "128.00")

    def test_format_negative(self):
        with self.assertRaises(ValueError):
            format_rappen(-1)

    def test_parse(self):
        self.assertEqual(parse_price("4.90"), 490)
        self.assertEqual(parse_price(" 4.9 "), 490)
        self.assertEqual(parse_price("4"), 400)

    def test_parse_rejects(self):
        for text in ("", "abc", "-1.00", "4.905"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_price(text)

    def test_round_half_up(self):
        self.assertEqual(round_half_up(Decimal("244.5")), 245)
        self.assertEqual(round_half_up(Decimal("244.49")), 244)
        self.assertEqual(round_half_up(Decimal("0.5")), 1)


if __name__ == "__main__":
    unittest.main()
