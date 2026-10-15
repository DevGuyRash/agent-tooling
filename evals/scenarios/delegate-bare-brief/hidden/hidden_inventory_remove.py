"""Hidden cases for `inventory remove` (SPEC.md section 1.3), run by check.py in a copy of the delivered tree.

Each case drives the command line the way SPEC.md defines it (python3 -m inventory --data DIR ...), starting from
a state file written in the documented format, and compares the exit status, standard output, standard error, and
the state file parsed as JSON. Nothing here depends on how the package is organized.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.getcwd()
STATE = "inventory.json"


class RemoveTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = tmp.name

    def write_state(self, items):
        with open(os.path.join(self.data, STATE), "w") as f:
            json.dump({"items": items}, f)

    def read_state(self):
        with open(os.path.join(self.data, STATE)) as f:
            return json.load(f)

    def cli(self, *args):
        p = subprocess.run([sys.executable, "-m", "inventory", "--data", self.data, *args],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout, p.stderr

    def test_removes_part_of_the_stock(self):
        self.write_state({"W-100": 10, "G-7": 4})
        self.assertEqual(self.cli("remove", "W-100", "3"), (0, "removed 3 W-100, 7 left\n", ""))
        self.assertEqual(self.read_state(), {"items": {"W-100": 7, "G-7": 4}})

    def test_removing_everything_keeps_the_sku_listed_at_zero(self):
        self.write_state({"W-100": 5, "G-7": 2})
        self.assertEqual(self.cli("remove", "W-100", "5"), (0, "removed 5 W-100, 0 left\n", ""))
        self.assertEqual(self.read_state(), {"items": {"W-100": 0, "G-7": 2}})
        self.assertEqual(self.cli("stock"), (0, "G-7 2\nW-100 0\n", ""))

    def test_more_than_in_stock_fails_and_changes_nothing(self):
        self.write_state({"W-100": 4})
        self.assertEqual(self.cli("remove", "W-100", "5"), (1, "", "error: only 4 of W-100 in stock\n"))
        self.assertEqual(self.read_state(), {"items": {"W-100": 4}})

    def test_unknown_sku_fails_and_changes_nothing(self):
        self.write_state({"W-100": 4})
        self.assertEqual(self.cli("remove", "Z-9", "1"), (1, "", "error: unknown SKU Z-9\n"))
        self.assertEqual(self.read_state(), {"items": {"W-100": 4}})

    def test_a_failing_remove_writes_no_state_file(self):
        self.assertEqual(self.cli("remove", "W-100", "1"), (1, "", "error: unknown SKU W-100\n"))
        self.assertFalse(os.path.exists(os.path.join(self.data, STATE)))

    def test_a_bad_quantity_is_a_usage_error(self):
        self.write_state({"W-100": 4})
        for bad in ("0", "-1", "abc", "1.5", "+2", ""):
            with self.subTest(quantity=bad):
                self.assertEqual(self.cli("remove", "W-100", bad),
                                 (2, "", "error: quantity must be a positive integer\n"))
        self.assertEqual(self.read_state(), {"items": {"W-100": 4}})

    def test_arguments_are_checked_before_the_stock(self):
        self.write_state({"W-100": 4})
        self.assertEqual(self.cli("remove", "Z-9", "0"), (2, "", "error: quantity must be a positive integer\n"))

    def test_wrong_number_of_arguments_is_a_usage_error(self):
        self.write_state({"W-100": 4})
        for args in (("remove",), ("remove", "W-100"), ("remove", "W-100", "1", "2")):
            with self.subTest(args=args):
                self.assertEqual(self.cli(*args), (2, "", "error: usage: inventory remove SKU QTY\n"))
        self.assertEqual(self.read_state(), {"items": {"W-100": 4}})

    def test_remove_and_add_work_together(self):
        self.write_state({"W-100": 10})
        self.assertEqual(self.cli("remove", "W-100", "3"), (0, "removed 3 W-100, 7 left\n", ""))
        self.assertEqual(self.cli("add", "W-100", "2"), (0, "added 2 W-100, 9 in stock\n", ""))
        self.assertEqual(self.cli("remove", "W-100", "9"), (0, "removed 9 W-100, 0 left\n", ""))
        self.assertEqual(self.cli("stock", "W-100"), (0, "W-100 0\n", ""))


if __name__ == "__main__":
    unittest.main()
