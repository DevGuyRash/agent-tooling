import unittest


class LeftoverTest(unittest.TestCase):
    def test_not_finished(self):
        self.assertEqual(1 + 1, 3)


if __name__ == "__main__":
    unittest.main()
