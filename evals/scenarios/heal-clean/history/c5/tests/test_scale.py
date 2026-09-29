import unittest
from fractions import Fraction

from pantry.scale import format_quantity, parse_quantity, scale_line


class ScaleTest(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(scale_line("2 cups flour", 1.5), "3 cups flour")

    def test_fraction_output(self):
        self.assertEqual(scale_line("1 tbsp sugar", 0.5), "1/2 tbsp sugar")
        self.assertEqual(format_quantity(Fraction(7, 3)), "2 1/3")

    def test_mixed_numbers(self):
        self.assertEqual(parse_quantity("1 1/2"), Fraction(3, 2))
        self.assertEqual(scale_line("1 1/2 cups flour", 2), "3 cups flour")

    def test_count_without_unit(self):
        self.assertEqual(scale_line("1 egg", 3), "3 egg")

    def test_non_ingredient_lines_unchanged(self):
        self.assertEqual(scale_line("Pancakes (serves 4)", 2), "Pancakes (serves 4)")

    def test_metric(self):
        self.assertEqual(scale_line("1 cup milk", 1, metric=True), "237 ml milk")
        self.assertEqual(scale_line("4 oz cheese", 1, metric=True), "113 g cheese")


if __name__ == "__main__":
    unittest.main()
