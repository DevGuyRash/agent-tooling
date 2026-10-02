import contextlib
import io
import unittest
from pathlib import Path

from shelftag.cli import main, read_items

ITEMS = Path(__file__).parent / "data" / "items.csv"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def test_read_items(self):
        items = read_items(ITEMS)
        self.assertEqual(len(items), 5)
        self.assertEqual((items[1].name, items[1].price_rappen, items[1].net_grams, items[1].origin),
                         ("Ruchbrot", 360, 500, None))

    def test_print(self):
        code, out, _ = run("print", str(ITEMS))
        self.assertEqual(code, 0)
        labels = out.rstrip("\n").split("\n\n")
        self.assertEqual(len(labels), 5)
        self.assertEqual(labels[0], "Bio Bergkäse\nCHF 4.90\nCHF 2.45 / 100 g\nHerkunft: Schweiz")
        self.assertEqual(labels[3], "Basler Läckerli Original im Ges…\nCHF 12.80\nHerkunft: Schweiz")

    def test_print_width(self):
        code, out, _ = run("print", str(ITEMS), "--width", "20")
        self.assertEqual(code, 0)
        self.assertIn("Haferdrink ungesüsst\nCHF 2.25\nCHF 2.25 / kg\nHerkunft: Schweden", out)

    def test_preview(self):
        self.assertEqual(run("preview", "Zitronen", "0.65"), (0, "Zitronen\nCHF 0.65\n", ""))

    def test_bad_price(self):
        code, out, err = run("preview", "Zitronen", "x")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("not a price", err)

    def test_missing_file(self):
        code, _, err = run("print", "/nonexistent/items.csv")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("shelftag: "))


if __name__ == "__main__":
    unittest.main()
