import contextlib
import io
import os
import tempfile
import unittest

from shiftboard.cli import main

ROSTER = """date,start,end,station,volunteer
2026-09-14,09:00,12:00,Prep,Amara Okafor
2026-09-14,12:00,15:00,Dish pit,Tomasz Nowak
2026-09-16,17:00,20:30,Serving,Amara Okafor
"""


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def roster(self, text=ROSTER):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_check(self):
        self.assertEqual(self.run_cli("check", self.roster()), (0, "3 shifts from 2026-09-14 to 2026-09-16\n", ""))

    def test_hours(self):
        code, out, _ = self.run_cli("hours", self.roster())
        self.assertEqual(code, 0)
        self.assertEqual(out, "Volunteer     Shifts  Hours\n"
                              "------------  ------  -----\n"
                              "Amara Okafor  2       6.5\n"
                              "Tomasz Nowak  1       3.0\n")

    def test_roster_error(self):
        path = self.roster("date,start,end,station,volunteer\n2026-09-14,09:00,12:00,Prep\n")
        self.assertEqual(self.run_cli("check", path), (1, "", f"shiftboard: {path}:2: expected 5 fields, found 4\n"))

    def test_missing_roster(self):
        code, out, err = self.run_cli("check", "/nonexistent/roster.csv")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("shiftboard: cannot read /nonexistent/roster.csv"))
