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

    def test_cancel_marks_an_open_order_cancelled(self):
        run(self.data, "place", "alice", "W-100:2")
        self.assertEqual(run(self.data, "cancel", "1"), (0, "cancelled order 1\n", ""))
        self.assertEqual(run(self.data, "cancel", "1"), (1, "", "error: order 1 is already cancelled\n"))
        self.assertEqual(run(self.data, "cancel", "9"), (1, "", "error: no such order 9\n"))

    def test_list_filters_by_status(self):
        run(self.data, "place", "alice", "W-100:2")
        run(self.data, "place", "bob", "A-1:1", "B-2:3")
        run(self.data, "cancel", "1")
        self.assertEqual(run(self.data, "list"), (0, "1 alice cancelled 1 line\n2 bob open 2 lines\n", ""))
        self.assertEqual(run(self.data, "list", "--status", "open"), (0, "2 bob open 2 lines\n", ""))
        self.assertEqual(run(self.data, "list", "--status", "lost"), (2, "", "error: unknown status lost\n"))


if __name__ == "__main__":
    unittest.main()
