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


if __name__ == "__main__":
    unittest.main()
