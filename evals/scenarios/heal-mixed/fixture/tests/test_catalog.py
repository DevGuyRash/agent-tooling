import unittest

from helpers import TempCatalog


class CatalogTest(unittest.TestCase):
    def test_add_and_save(self):
        with TempCatalog() as t:
            t.catalog.add("9780306406157", "Title", "Author")
            t.catalog.save()
            self.assertEqual(t.reload().find("9780306406157")["title"], "Title")

    def test_duplicate_rejected(self):
        with TempCatalog() as t:
            t.catalog.add("9780306406157", "Title", "Author")
            with self.assertRaises(ValueError):
                t.catalog.add("9780306406157", "Title", "Author")

    def test_tag_is_idempotent(self):
        with TempCatalog() as t:
            t.catalog.add("9780306406157", "Title", "Author")
            t.catalog.tag("9780306406157", ["sf", "sf", "classic"])
            self.assertEqual(t.catalog.find("9780306406157")["tags"], ["sf", "classic"])

    def test_tag_unknown_book(self):
        with TempCatalog() as t:
            with self.assertRaises(KeyError):
                t.catalog.tag("9780306406157", ["sf"])


if __name__ == "__main__":
    unittest.main()
