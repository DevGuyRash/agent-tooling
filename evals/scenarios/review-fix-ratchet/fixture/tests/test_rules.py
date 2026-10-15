import unittest

from stampcard.rules import stamps_for


class StampsForTest(unittest.TestCase):
    def test_one_stamp_per_full_four_and_three_at_most(self):
        self.assertEqual([stamps_for(c) for c in (399, 400, 799, 800, 1200, 5000)], [0, 1, 1, 2, 3, 3])


if __name__ == "__main__":
    unittest.main()
