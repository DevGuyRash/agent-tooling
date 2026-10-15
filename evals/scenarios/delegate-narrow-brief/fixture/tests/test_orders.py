import contextlib
import io
import tempfile
import unittest

from orders.cli import main


def run(data, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(["--data", data, *args])
    return code, out.getvalue(), err.getvalue()


class OrdersTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = tmp.name

    def test_place_numbers_orders_from_one(self):
        self.assertEqual(run(self.data, "place", "alice", "W-100:2"), (0, "placed order 1 for alice\n", ""))
        self.assertEqual(run(self.data, "place", "bob", "A-1:1", "B-2:3"), (0, "placed order 2 for bob\n", ""))

    def test_place_rejects_bad_lines(self):
        self.assertEqual(run(self.data, "place", "alice", "W-100"), (2, "", 'error: bad line "W-100": expected SKU:QTY\n'))
        self.assertEqual(run(self.data, "place", "alice", "W-100:0"), (2, "", "error: quantity must be a positive integer\n"))

    def test_show_prints_the_order(self):
        run(self.data, "place", "bob", "A-1:1", "B-2:3")
        self.assertEqual(run(self.data, "show", "1"), (0, "order 1 bob open\n  A-1 x1\n  B-2 x3\n", ""))
        self.assertEqual(run(self.data, "show", "9"), (1, "", "error: no such order 9\n"))


if __name__ == "__main__":
    unittest.main()
