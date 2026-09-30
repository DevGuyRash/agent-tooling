import contextlib
import io
import unittest

from cli import report


class ReportTest(unittest.TestCase):
    def test_report_prints_total_for_unique_rows(self):
        rows = [{"order_id": "A1", "amount": 10}, {"order_id": "A2", "amount": 20}]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report(rows)
        self.assertIn("30", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
