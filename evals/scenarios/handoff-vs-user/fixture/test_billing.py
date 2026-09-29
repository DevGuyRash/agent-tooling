import unittest

from legacy.billing import to_cents


class ToCentsTest(unittest.TestCase):
    def test_whole(self):
        self.assertEqual(to_cents(2), 200)

    def test_rounds_half_up(self):
        self.assertEqual(to_cents(1.005), 101)
        self.assertEqual(to_cents(0.125), 13)

    def test_rounds_down_below_half(self):
        self.assertEqual(to_cents(1.004), 100)


if __name__ == "__main__":
    unittest.main()
