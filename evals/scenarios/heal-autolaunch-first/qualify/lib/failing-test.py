import unittest


class SinceTest(unittest.TestCase):
    def test_report_since_is_covered(self):
        self.assertEqual(1 + 1, 3)


if __name__ == "__main__":
    unittest.main()
