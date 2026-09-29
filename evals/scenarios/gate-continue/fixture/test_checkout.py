import unittest

from checkout import total


class TotalTest(unittest.TestCase):
    def test_no_discount(self):
        self.assertEqual(total([10, 20]), 30)

    def test_discount_applied_once(self):
        self.assertEqual(total([10, 20], 0.1), 27.0)


if __name__ == "__main__":
    unittest.main()
