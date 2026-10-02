import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from shopcrm.cli import main

SAMPLE = str(Path(__file__).resolve().parent / "data" / "sample-export.csv")
HEADER = "customer_id,created_at,first_name,last_name,email,phone,orders,total_spent,accepts_marketing\n"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ValidateTest(unittest.TestCase):
    def test_sample_is_valid(self):
        code, out, _ = run("validate", SAMPLE)
        self.assertEqual(code, 0)
        self.assertIn("ok", out)

    def test_reports_every_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text(HEADER + "1,2024-01-01T00:00:00Z,A,B,,,x,1.00,no\n"
                            "1,2024-01-02T00:00:00Z,A,B,,,1,1.00,maybe\n")
            code, _, err = run("validate", str(path))
        self.assertEqual(code, 1)
        self.assertIn("bad.csv:2: orders is not a count", err)
        self.assertIn("bad.csv:3: accepts_marketing must be yes or no", err)
        self.assertIn("bad.csv:3: customer_id 1 appears twice", err)


class LookupTest(unittest.TestCase):
    def test_prints_matching_rows(self):
        code, out, _ = run("lookup", SAMPLE, "+1 (206) 555-0110")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0], HEADER.strip())
        self.assertEqual([line.split(",")[0] for line in lines[1:]], ["2001", "2003", "2008"])

    def test_no_match(self):
        code, out, err = run("lookup", SAMPLE, "nobody@example.com")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no rows match", err)


class StatsTest(unittest.TestCase):
    def test_counts(self):
        code, out, _ = run("stats", SAMPLE)
        self.assertEqual(code, 0)
        self.assertIn("rows               8\n", out)
        self.assertIn("distinct emails    5\n", out)
        self.assertIn("with phone         5\n", out)
        self.assertIn("total spent        580.14\n", out)


class ErrorsTest(unittest.TestCase):
    def test_missing_file(self):
        code, _, err = run("stats", "/nonexistent/customers.csv")
        self.assertEqual(code, 1)
        self.assertIn("No such file", err)


if __name__ == "__main__":
    unittest.main()
