import unittest

from circdesk.money import fmt


class FmtTest(unittest.TestCase):
    def test_cents(self):
        self.assertEqual(fmt(0), "0.00")
        self.assertEqual(fmt(5), "0.05")
        self.assertEqual(fmt(75), "0.75")
        self.assertEqual(fmt(1250), "12.50")
        self.assertEqual(fmt(100000), "1000.00")


if __name__ == "__main__":
    unittest.main()
