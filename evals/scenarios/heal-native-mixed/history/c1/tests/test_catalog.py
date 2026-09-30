import tempfile
import unittest
from pathlib import Path

from shelfmark.catalog import Catalog


class CatalogTest(unittest.TestCase):
    def test_add_and_save(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cat.json"
            cat = Catalog(path)
            cat.add("9780306406157", "Title", "Author")
            cat.save()
            self.assertEqual(Catalog(path).find("9780306406157")["title"], "Title")

    def test_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            cat = Catalog(Path(d) / "cat.json")
            cat.add("9780306406157", "Title", "Author")
            with self.assertRaises(ValueError):
                cat.add("9780306406157", "Title", "Author")


if __name__ == "__main__":
    unittest.main()
