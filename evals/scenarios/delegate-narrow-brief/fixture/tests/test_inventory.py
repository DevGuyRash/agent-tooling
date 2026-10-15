import contextlib
import io
import tempfile
import unittest

from inventory.cli import main


def run(data, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(["--data", data, *args])
    return code, out.getvalue(), err.getvalue()


class InventoryTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = tmp.name

    def test_add_creates_a_sku_and_accumulates(self):
        self.assertEqual(run(self.data, "add", "W-100", "5"), (0, "added 5 W-100, 5 in stock\n", ""))
        self.assertEqual(run(self.data, "add", "W-100", "7"), (0, "added 7 W-100, 12 in stock\n", ""))

    def test_add_rejects_a_bad_quantity(self):
        for bad in ("0", "-2", "x", "1.5"):
            self.assertEqual(run(self.data, "add", "W-100", bad), (2, "", "error: quantity must be a positive integer\n"))

    def test_stock_lists_skus_in_order(self):
        run(self.data, "add", "B-2", "1")
        run(self.data, "add", "A-1", "3")
        self.assertEqual(run(self.data, "stock"), (0, "A-1 3\nB-2 1\n", ""))
        self.assertEqual(run(self.data, "stock", "A-1"), (0, "A-1 3\n", ""))

    def test_stock_of_an_unknown_sku_fails(self):
        self.assertEqual(run(self.data, "stock", "Z-9"), (1, "", "error: unknown SKU Z-9\n"))


if __name__ == "__main__":
    unittest.main()
