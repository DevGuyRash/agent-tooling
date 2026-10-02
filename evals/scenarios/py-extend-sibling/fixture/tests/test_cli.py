"""deskd's command line, run as the ops scripts run it: python3 -m deskd from the repository root."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = "tests/data/tickets.jsonl"


def deskd(*args):
    return subprocess.run([sys.executable, "-m", "deskd", *args], cwd=ROOT, capture_output=True, text=True,
                          timeout=60)


class ShowTest(unittest.TestCase):
    def test_show_prints_the_ticket(self):
        r = deskd("show", "--store", STORE, "4182")
        self.assertEqual(r.returncode, 0, r.stderr)
        view = json.loads(r.stdout)
        self.assertEqual(view["id"], 4182)
        self.assertEqual(view["subject"], "Invoices export times out")
        self.assertEqual(view["priority"], "P2")
        self.assertEqual(view["priority_label"], "High")
        self.assertEqual(view["opened_at"], "2026-10-02T16:45:12")

    def test_unlabelled_priority_shows_as_is(self):
        view = json.loads(deskd("show", "--store", STORE, "4195").stdout)
        self.assertEqual(view["priority_label"], "-")
        self.assertEqual(view["subject"], "Löschung meines Kontos")

    def test_unknown_ticket(self):
        r = deskd("show", "--store", STORE, "9999")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no ticket 9999", r.stderr)


class ListTest(unittest.TestCase):
    def test_list_in_id_order(self):
        r = deskd("list", "--store", STORE)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            "  4101  P3  solved   2026-09-28T13:55  Wrong VAT on September invoice",
            "  4177  P1  pending  2026-10-01T09:03  Cannot reset password",
            "  4182  P2  open     2026-10-02T16:45  Invoices export times out",
            "  4190  P4  open     2026-10-03T11:20  Feature request: dark mode",
            "  4195  -   open     2026-10-04T08:00  Löschung meines Kontos",
        ])

    def test_list_by_status(self):
        r = deskd("list", "--store", STORE, "--status", "open")
        self.assertEqual([line.split()[0] for line in r.stdout.splitlines()], ["4182", "4190", "4195"])


class ExportTest(unittest.TestCase):
    def test_one_object_per_ticket(self):
        r = deskd("export", "--store", STORE)
        self.assertEqual(r.returncode, 0, r.stderr)
        views = [json.loads(line) for line in r.stdout.splitlines()]
        self.assertEqual([v["id"] for v in views], [4101, 4177, 4182, 4190, 4195])
        self.assertEqual(views[1]["status"], "pending")
        self.assertEqual(views[3]["priority_label"], "Low")


class ErrorTest(unittest.TestCase):
    def test_bad_store(self):
        r = deskd("export", "--store", "tests/data/broken.jsonl")
        self.assertEqual(r.returncode, 2)
        self.assertIn("broken.jsonl line 2: unknown status 'waiting'", r.stderr)

    def test_missing_config(self):
        r = deskd("--config", "tests/data/no-such-dir", "export", "--store", STORE)
        self.assertEqual(r.returncode, 2)
        self.assertIn("cannot read", r.stderr)


if __name__ == "__main__":
    unittest.main()
