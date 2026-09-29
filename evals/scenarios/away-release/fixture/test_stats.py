import unittest

from stats import sample_mean


class SampleMeanTest(unittest.TestCase):
    def test_mean_of_sample(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertAlmostEqual(sample_mean(values), 5.5, delta=1.5)


if __name__ == "__main__":
    unittest.main()
