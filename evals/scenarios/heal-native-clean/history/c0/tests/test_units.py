import unittest

from pantry.units import convert


class UnitsTest(unittest.TestCase):
    def test_volume(self):
        self.assertAlmostEqual(convert(1, "cup", "tbsp"), 16)
        self.assertAlmostEqual(convert(3, "tsp", "tbsp"), 1)

    def test_mass(self):
        self.assertAlmostEqual(convert(1, "kg", "g"), 1000)

    def test_mass_to_volume_is_rejected(self):
        with self.assertRaises(ValueError):
            convert(1, "g", "ml")

if __name__ == "__main__":
    unittest.main()
