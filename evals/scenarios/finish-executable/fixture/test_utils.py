import unittest

from utils import chunk, parse_duration, slugify


class UtilsTest(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("  Hello, World! 2026 "), "hello-world-2026")
        self.assertEqual(slugify("a  --  b"), "a-b")

    def test_chunk(self):
        self.assertEqual(chunk([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])
        self.assertEqual(chunk([], 3), [])

    def test_parse_duration(self):
        self.assertEqual(parse_duration("1h30m"), 5400)
        self.assertEqual(parse_duration("45s"), 45)
        self.assertEqual(parse_duration("2h5s"), 7205)


if __name__ == "__main__":
    unittest.main()
