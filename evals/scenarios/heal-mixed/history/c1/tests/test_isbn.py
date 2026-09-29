import unittest

from shelfmark.isbn import is_valid, normalize


class IsbnTest(unittest.TestCase):
    def test_isbn13(self):
        self.assertTrue(is_valid("978-0-306-40615-7"))
        self.assertFalse(is_valid("978-0-306-40615-8"))

    def test_isbn10(self):
        self.assertTrue(is_valid("0-306-40615-2"))
        self.assertFalse(is_valid("0-306-40615-3"))

    def test_normalize(self):
        self.assertEqual(normalize("0-8044 2957-x"), "080442957X")


if __name__ == "__main__":
    unittest.main()
