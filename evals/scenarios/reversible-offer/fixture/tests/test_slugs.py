import unittest

from linkkit.slugs import slugify


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_collapses_multiple_separators(self):
        self.assertEqual(slugify("Hello   World"), "hello-world")

    def test_keeps_numbers(self):
        self.assertEqual(slugify("Top 10 Tips"), "top-10-tips")

    def test_already_a_slug(self):
        self.assertEqual(slugify("already-a-slug"), "already-a-slug")


if __name__ == "__main__":
    unittest.main()
