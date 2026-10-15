import unittest

from stallbook.sales import load_week

from .helpers import data_dir

ROWS = [
    ["2026-W13", "Honey", "preserves", 9, 900],
    ["2026-W14", "Rye roll", "bread", 30, 120],
    ["2026-W14", "Honey", "preserves", 4, 900],
    ["2026-W14", "Sourdough loaf", "bread", 12, 450],
    ["2026-W14", "Sourdough loaf", "bread", 3, 480],
    ["2026-W14", "Apple cake", "bread", 6, 600],
]


class LoadWeekTest(unittest.TestCase):
    def test_totals_one_week_per_item(self):
        report = load_week(data_dir(ROWS), "2026-W14")
        by_item = {line.item: line for line in report.lines}
        self.assertEqual(set(by_item), {"Rye roll", "Honey", "Sourdough loaf", "Apple cake"})
        self.assertEqual(by_item["Sourdough loaf"].units, 15)
        self.assertEqual(by_item["Sourdough loaf"].revenue_cents, 12 * 450 + 3 * 480)
        self.assertEqual(report.total_units, 55)
        self.assertEqual(report.total_revenue_cents, 3600 + 3600 + 6840 + 3600)

    def test_best_revenue_first_ties_by_name(self):
        report = load_week(data_dir(ROWS), "2026-W14")
        self.assertEqual([line.item for line in report.lines], ["Sourdough loaf", "Apple cake", "Honey", "Rye roll"])

    def test_week_without_sales_is_empty(self):
        report = load_week(data_dir(ROWS), "2026-W20")
        self.assertEqual(report.lines, ())
        self.assertEqual(report.total_revenue_cents, 0)


if __name__ == "__main__":
    unittest.main()
