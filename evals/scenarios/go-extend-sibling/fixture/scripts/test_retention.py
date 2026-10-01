"""Tests for retention.py. Run with: python3 -m unittest discover -s scripts"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retention  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retention.py")


def catalog(*rows):
    return ["\t".join(r) + "\n" for r in rows]


def snap(id_, created, state="ok", host="db-1", set_="pgdump", tags="-"):
    return (id_, host, set_, created, "100", state, tags)


def policy(**counts):
    return {rule: counts.get(rule, 0) for rule in retention.RULES}


class DecideTest(unittest.TestCase):
    def decide(self, rows, **counts):
        snaps = retention.read_catalog(catalog(*rows), "t.tsv")
        return retention.decide(snaps, policy(**counts))

    def test_daily_keeps_the_newest_of_each_day(self):
        kept = self.decide([snap("a", "2026-01-05T02:00:00Z"), snap("b", "2026-01-05T14:00:00Z"),
                            snap("c", "2026-01-06T02:00:00Z"), snap("d", "2026-01-04T02:00:00Z")], daily=2)
        self.assertEqual(kept, {"a": [], "b": ["daily"], "c": ["daily"], "d": []})

    def test_days_are_utc(self):
        # 01:30 at +02:00 is 23:30 UTC the day before.
        kept = self.decide([snap("a", "2026-01-06T01:30:00+02:00"), snap("b", "2026-01-05T20:00:00Z")], daily=5)
        self.assertEqual(kept, {"a": ["daily"], "b": []})

    def test_weeks_are_iso_weeks(self):
        # Monday 2025-12-29 and Friday 2026-01-02 are both in week 1 of 2026.
        kept = self.decide([snap("a", "2025-12-29T02:00:00Z"), snap("b", "2026-01-02T02:00:00Z"),
                            snap("c", "2025-12-28T02:00:00Z")], weekly=5)
        self.assertEqual(kept, {"a": [], "b": ["weekly"], "c": ["weekly"]})

    def test_rules_are_independent_and_listed_in_order(self):
        kept = self.decide([snap("a", "2026-01-05T02:00:00Z"), snap("b", "2026-02-01T02:00:00Z")],
                           last=1, daily=1, weekly=2, monthly=2)
        self.assertEqual(kept, {"a": ["weekly", "monthly"], "b": ["last", "daily", "weekly", "monthly"]})

    def test_partial_and_failed_are_deleted(self):
        kept = self.decide([snap("a", "2026-01-05T02:00:00Z"), snap("b", "2026-01-06T02:00:00Z", "partial"),
                            snap("c", "2026-01-07T02:00:00Z", "failed")], last=5)
        self.assertEqual(kept, {"a": ["last"], "b": [], "c": []})

    def test_series_are_separate(self):
        kept = self.decide([snap("a", "2026-01-05T02:00:00Z"), snap("b", "2026-01-05T03:00:00Z", host="db-2")],
                           last=1)
        self.assertEqual(kept, {"a": ["last"], "b": ["last"]})

    def test_same_second_orders_by_id(self):
        kept = self.decide([snap("b", "2026-01-05T02:00:00Z"), snap("a", "2026-01-05T02:00:00Z")], last=1)
        self.assertEqual(kept, {"a": ["last"], "b": []})

    def test_bad_line_names_the_line(self):
        with self.assertRaisesRegex(retention.CatalogError, r"t\.tsv line 2: bad state 'done'"):
            retention.read_catalog(["# header\n"] + catalog(snap("a", "2026-01-05T02:00:00Z", "done")), "t.tsv")


class CommandTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".tsv")
        with os.fdopen(fd, "w") as fh:
            fh.writelines(catalog(snap("s-3", "2026-01-07T02:00:00Z"), snap("s-1", "2026-01-05T02:00:00Z"),
                                  snap("s-2", "2026-01-06T02:00:00Z", "failed"),
                                  snap("s-4", "2026-01-04T02:00:00Z", host="web-1", set_="etc")))

    def tearDown(self):
        os.unlink(self.path)

    def run_script(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)

    def test_prints_ids_to_delete_in_catalog_order(self):
        r = self.run_script("--last", "1", self.path)
        self.assertEqual((r.returncode, r.stdout), (0, "s-1\ns-2\n"))

    def test_host_filter(self):
        r = self.run_script("--last", "1", "--host", "db-1", self.path)
        self.assertEqual(r.stdout, "s-1\ns-2\n")

    def test_json(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(retention.main(["--daily", "1", "--json", self.path]), 0)
        rows = json.loads(out.getvalue())
        self.assertEqual([(r["id"], r["keep"], r["rules"]) for r in rows],
                         [("s-3", True, ["daily"]), ("s-1", False, []), ("s-2", False, []), ("s-4", True, ["daily"])])

    def test_refuses_without_a_rule(self):
        r = self.run_script(self.path)
        self.assertEqual(r.returncode, 2)
        self.assertIn("refusing", r.stderr)

    def test_unreadable_catalog(self):
        r = self.run_script("--daily", "1", self.path + ".missing")
        self.assertEqual((r.returncode, r.stdout), (1, ""))


if __name__ == "__main__":
    unittest.main()
