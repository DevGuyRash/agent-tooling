import unittest
from decimal import Decimal

from invoicing.money import fmt, to_pennies


class MoneyTest(unittest.TestCase):
    def test_rounds_half_up(self):
        for amount, pennies in [("0.125", "0.13"), ("0.135", "0.14"), ("2.675", "2.68"), ("0.124", "0.12"),
                                ("-0.125", "-0.13"), ("7", "7.00")]:
            with self.subTest(amount=amount):
                self.assertEqual(to_pennies(Decimal(amount)), Decimal(pennies))

    def test_fmt(self):
        self.assertEqual(fmt(Decimal("1234.5")), "1,234.50")
        self.assertEqual(fmt(Decimal("0")), "0.00")
