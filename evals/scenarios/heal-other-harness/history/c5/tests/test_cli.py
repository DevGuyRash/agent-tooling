import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import ts
from meterwatch.cli import main


def write_events(rows):
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for when, key, units in rows:
        handle.write(json.dumps({"ts": when, "key": key, "units": units}) + "\n")
    handle.close()
    return handle.name


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class DailyCommandTest(unittest.TestCase):
    def events(self, rows):
        path = write_events(rows)
        self.addCleanup(Path(path).unlink)
        return path

    def test_daily_prints_one_line_per_day_and_key(self):
        path = self.events([(ts("2026-03-01 09:00"), "acme", 4), (ts("2026-03-01 23:30"), "beta", 2), (ts("2026-03-02 08:15"), "acme", 5)])
        code, out = run("daily", path)
        self.assertEqual((code, out), (0, "2026-03-01  acme  4\n2026-03-01  beta  2\n2026-03-02  acme  5\n"))

    def test_key_option_limits_the_output(self):
        path = self.events([(ts("2026-03-01 09:00"), "acme", 4), (ts("2026-03-01 10:00"), "beta", 2), (ts("2026-03-02 09:00"), "acme", 5)])
        code, out = run("daily", path, "--key", "beta")
        self.assertEqual((code, out), (0, "2026-03-01  beta  2\n"))

    def test_total_ends_the_report(self):
        path = self.events([(ts("2026-03-01 09:00"), "acme", 4), (ts("2026-03-02 09:00"), "beta", 6)])
        code, out = run("daily", path, "--total")
        self.assertEqual((code, out), (0, "2026-03-01  acme  4\n2026-03-02  beta  6\ntotal  10\n"))


class InvoiceCommandTest(unittest.TestCase):
    def test_invoice_prices_each_line_and_totals(self):
        path = write_events([(1772325000, "acme", 10), (1772452800, "acme", 20)])
        self.addCleanup(Path(path).unlink)
        code, out = run("invoice", path, "--rate", "0.5")
        self.assertEqual((code, out), (0, "2026-03-01  acme  10  5.00\n2026-03-02  acme  20  10.00\ntotal  15.00\n"))


class TopCommandTest(unittest.TestCase):
    def test_top_lists_the_busiest_keys(self):
        path = write_events([(1772325000, "acme", 4), (1772325100, "beta", 9), (1772325200, "acme", 7), (1772325300, "gamma", 1)])
        self.addCleanup(Path(path).unlink)
        code, out = run("top", path, "-n", "2")
        self.assertEqual((code, out), (0, "acme  11\nbeta  9\n"))
