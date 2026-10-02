import unittest

from shopcrm.money import format_money, parse_money


class MoneyTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_money("120"), 12000)
        self.assertEqual(parse_money("120.5"), 12050)
        self.assertEqual(parse_money("120.05"), 12005)
        self.assertEqual(parse_money(" 0.99 "), 99)
        self.assertEqual(parse_money("-3.10"), -310)

    def test_parse_rejects(self):
        for text in ("", "1,200.00", "12.345", "$5", "abc"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_money(text)

    def test_format(self):
        self.assertEqual(format_money(12000), "120.00")
        self.assertEqual(format_money(5), "0.05")
        self.assertEqual(format_money(-310), "-3.10")
        self.assertEqual(format_money(123456789), "1234567.89")


if __name__ == "__main__":
    unittest.main()
