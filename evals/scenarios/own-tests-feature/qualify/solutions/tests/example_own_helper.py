import contextlib
import datetime
import io
import unittest
from pathlib import Path

from shiftboard import roster
from shiftboard.board import render_week, week_start
from shiftboard.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "examples"


class WeekBoardTest(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_doc_example(self):
        code, out, err = self.run_cli("week", str(EXAMPLES / "roster-sample.csv"), "2026-W38")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, (EXAMPLES / "week-2026-W38.txt").read_text(encoding="utf-8"))

    def test_render_week_gives_the_example_without_final_newline(self):
        shifts = roster.load(EXAMPLES / "roster-sample.csv")
        expected = (EXAMPLES / "week-2026-W38.txt").read_text(encoding="utf-8")
        self.assertEqual(render_week(shifts, "2026-W38") + "\n", expected)

    def test_empty_week(self):
        self.assertEqual(self.run_cli("week", str(EXAMPLES / "roster-sample.csv"), "2026-W40"),
                         (0, "No shifts in 2026-W40.\n", ""))

    def test_bad_week(self):
        for week in ("2026-38", "2026-W54", "2025-W53"):
            with self.subTest(week=week):
                self.assertEqual(self.run_cli("week", str(EXAMPLES / "roster-sample.csv"), week),
                                 (2, "", f"shiftboard: bad week '{week}'\n"))

    def test_render_week_rejects_bad_week(self):
        with self.assertRaises(ValueError):
            render_week([], "2026-W00")


class WeekStartTest(unittest.TestCase):
    def test_week_one_can_start_in_december(self):
        self.assertEqual(week_start("2026-W01"), datetime.date(2025, 12, 29))
