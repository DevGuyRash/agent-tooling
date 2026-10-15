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

    def test_remove_takes_stock_out_and_keeps_the_sku_at_zero(self):
        run(self.data, "add", "W-100", "5")
        self.assertEqual(run(self.data, "remove", "W-100", "2"), (0, "removed 2 W-100, 3 left\n", ""))
        self.assertEqual(run(self.data, "remove", "W-100", "3"), (0, "removed 3 W-100, 0 left\n", ""))
        self.assertEqual(run(self.data, "stock"), (0, "W-100 0\n", ""))

    def test_remove_refuses_more_than_is_in_stock(self):
        run(self.data, "add", "W-100", "4")
        self.assertEqual(run(self.data, "remove", "W-100", "5"), (1, "", "error: only 4 of W-100 in stock\n"))
        self.assertEqual(run(self.data, "stock", "W-100"), (0, "W-100 4\n", ""))

    def test_remove_rejects_an_unknown_sku_and_a_bad_quantity(self):
        self.assertEqual(run(self.data, "remove", "Z-9", "1"), (1, "", "error: unknown SKU Z-9\n"))
        self.assertEqual(run(self.data, "remove", "Z-9", "0"), (2, "", "error: quantity must be a positive integer\n"))
        self.assertEqual(run(self.data, "remove", "Z-9"), (2, "", "error: usage: inventory remove SKU QTY\n"))


if __name__ == "__main__":
    unittest.main()
