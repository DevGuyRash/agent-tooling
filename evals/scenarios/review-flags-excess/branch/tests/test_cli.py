import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from toolroom.cli import main

from .support import LOANS, write_data


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def run_main(self, *argv, **files):
        write_data(self.dir.name, **files)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--data", self.dir.name, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_out_lists_the_loans_still_out_oldest_due_first(self):
        code, out, _ = self.run_main("out")
        self.assertEqual(code, 0)
        self.assertEqual(out, "L-1  Bram Okafor  Cordless drill  2026-10-04\nL-3  Dara Lindqvist  Ladder, 3 m  2026-10-12\n")

    def test_out_breaks_ties_by_loan_id(self):
        loans = LOANS + "L-0,M-2,T-2,2026-09-20,2026-10-04,\n"
        _, out, _ = self.run_main("out", loans=loans)
        self.assertEqual([line.split("  ")[0] for line in out.splitlines()], ["L-0", "L-1", "L-3"])

    def test_unusable_data_stops_the_run_with_status_2(self):
        code, out, err = self.run_main("out", loans="loan,member\n")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("loans.csv: line 1", err)

    def test_a_bad_date_argument_is_a_usage_error(self):
        write_data(self.dir.name)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["--data", self.dir.name, "--today", "tomorrow", "out"])
        self.assertEqual(caught.exception.code, 2)

    def test_overdue_prints_the_list(self):
        code, out, _ = self.run_main("--today", "2026-10-15", "overdue")
        self.assertEqual(code, 0)
        self.assertEqual(out, "L-1  Bram Okafor  Cordless drill  11  5.50\nL-3  Dara Lindqvist  Ladder, 3 m  3  1.50\n")

    def test_overdue_as_csv(self):
        _, out, _ = self.run_main("--today", "2026-10-15", "overdue", "--format", "csv")
        self.assertEqual(out, 'loan,member,tool,days,fine\nL-1,Bram Okafor,Cordless drill,11,5.50\nL-3,Dara Lindqvist,"Ladder, 3 m",3,1.50\n')

    def test_overdue_writes_the_notices(self):
        notices = Path(self.dir.name) / "notices"
        self.run_main("--today", "2026-10-15", "overdue", "--notices", str(notices))
        self.assertEqual(sorted(p.name for p in notices.iterdir()), ["M-1.txt", "M-3.txt"])


if __name__ == "__main__":
    unittest.main()
