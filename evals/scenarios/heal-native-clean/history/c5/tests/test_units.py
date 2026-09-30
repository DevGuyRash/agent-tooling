import unittest

from pantry.units import convert, to_metric


class UnitsTest(unittest.TestCase):
    def test_volume(self):
        self.assertAlmostEqual(convert(1, "cup", "tbsp"), 16)
        self.assertAlmostEqual(convert(3, "tsp", "tbsp"), 1)

    def test_mass(self):
        self.assertAlmostEqual(convert(1, "kg", "g"), 1000)

    def test_ounces_and_pounds(self):
        self.assertAlmostEqual(convert(1, "lb", "oz"), 16)
        self.assertAlmostEqual(convert(8, "ounces", "g"), 226.796185)

    def test_mass_to_volume_is_rejected(self):
        with self.assertRaises(ValueError):
            convert(1, "g", "ml")

    def test_to_metric(self):
        amount, unit = to_metric(1, "cups")
        self.assertEqual(unit, "ml")
        self.assertAlmostEqual(amount, 236.5882365)


if __name__ == "__main__":
    unittest.main()
