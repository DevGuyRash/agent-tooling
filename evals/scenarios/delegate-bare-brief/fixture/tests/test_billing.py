import contextlib
import io
import tempfile
import unittest

from billing.cli import main


def run(data, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(["--data", data, *args])
    return code, out.getvalue(), err.getvalue()


class BillingTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = tmp.name

    def test_invoice_records_the_total(self):
        self.assertEqual(run(self.data, "invoice", "1", "25.00"), (0, "invoiced order 1: 25.00 due\n", ""))

    def test_invoice_twice_fails(self):
        run(self.data, "invoice", "1", "25.00")
        self.assertEqual(run(self.data, "invoice", "1", "30.00"), (1, "", "error: order 1 is already invoiced\n"))

    def test_invoice_rejects_a_bad_amount(self):
        for bad in ("25", "25.5", "-1.00", "ten"):
            self.assertEqual(run(self.data, "invoice", "1", bad), (2, "", "error: amount must look like 12.50\n"))


if __name__ == "__main__":
    unittest.main()
