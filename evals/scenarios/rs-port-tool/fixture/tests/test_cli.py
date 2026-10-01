import subprocess
import sys
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
ROOT = DATA.parents[1]


def reqstat(*args, stdin=None):
    return subprocess.run([sys.executable, "-m", "reqstat", *args], cwd=ROOT, input=stdin,
                          capture_output=True, text=True)


class GoldenTest(unittest.TestCase):
    """The reports the nightly job diffs and the dashboard scrapes must not change."""

    def check(self, expected, *args):
        r = reqstat(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, (DATA / expected).read_text())

    def test_route_table(self):
        self.check("sample-route.txt", "tests/data/sample.log")

    def test_path_csv_by_p95(self):
        self.check("sample-path-p95.csv", "--by", "path", "--format", "csv", "--sort", "p95", "tests/data/sample.log")

    def test_status_window(self):
        self.check("sample-status-window.txt", "--by", "status", "--since", "2026-09-14T08:00:05Z",
                   "--until", "2026-09-14T08:00:20Z", "tests/data/sample.log")


class CliTest(unittest.TestCase):
    def test_reads_stdin(self):
        r = reqstat("--by", "method", stdin="ts=2026-09-14T08:00:00Z method=GET path=/ status=200 dur=2ms\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[1].split(), ["GET", "1", "0.0", "2.0", "2.0", "2.0", "2.0", "0", "B"])

    def test_strict_stops_at_first_malformed_line(self):
        r = reqstat("--strict", "tests/data/sample.log")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")
        self.assertIn("sample.log:12:", r.stderr)

    def test_missing_file(self):
        r = reqstat("tests/data/no-such.log")
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot read", r.stderr)

    def test_empty_input(self):
        r = reqstat(stdin="# nothing yet\n\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "ROUTE  COUNT  ERR%  P50  P95  P99  MAX  BYTES\n-- 0 requests in 0 groups\n")

    def test_bad_option_value(self):
        self.assertEqual(reqstat("--by", "host").returncode, 2)
        self.assertEqual(reqstat("--since", "yesterday").returncode, 2)
        self.assertEqual(reqstat("--top", "-1").returncode, 2)
