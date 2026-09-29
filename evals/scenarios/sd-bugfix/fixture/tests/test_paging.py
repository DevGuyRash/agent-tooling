import unittest

from paging import pages


class PagesTest(unittest.TestCase):
    def test_partial_last_page(self):
        self.assertEqual(pages([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

    def test_empty(self):
        self.assertEqual(pages([], 3), [])


if __name__ == "__main__":
    unittest.main()
