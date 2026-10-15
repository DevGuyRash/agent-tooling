import unittest

from stallbook.render import money, render_text
from stallbook.sales import Line, WeeklyReport

SETTINGS = {"currency": "EUR", "title": "Stall sales"}


class MoneyTest(unittest.TestCase):
    def test_two_decimals(self):
        self.assertEqual(money(0), "0.00")
        self.assertEqual(money(5), "0.05")
        self.assertEqual(money(123456), "1234.56")


class RenderTextTest(unittest.TestCase):
    def test_table_and_total(self):
        report = WeeklyReport("2026-W14", (Line("Rye roll", "bread", 30, 3600), Line("Honey", "preserves", 5, 4500)), 35, 8100)
        self.assertEqual(
            render_text(report, SETTINGS),
            "Stall sales, week 2026-W14 (EUR)\n"
            "\n"
            "Rye roll  bread         30      36.00\n"
            "Honey     preserves      5      45.00\n"
            "\n"
            "total: 35 units, 81.00\n",
        )

    def test_empty_week(self):
        self.assertEqual(
            render_text(WeeklyReport("2026-W20", (), 0, 0), SETTINGS),
            "Stall sales, week 2026-W20 (EUR)\n\n(no sales)\n",
        )


if __name__ == "__main__":
    unittest.main()
