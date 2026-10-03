import contextlib
import io
import unittest
from pathlib import Path

from shiftboard.cli import main

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent / "docs" / "examples"


class WeekBoardTest(unittest.TestCase):
    def test_doc_example(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["week", str(EXAMPLES / "roster-sample.csv"), "2026-W38"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), (HERE / "golden" / "week-2026-W38.txt").read_text(encoding="utf-8"))

    def test_empty_week(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["week", str(EXAMPLES / "roster-sample.csv"), "2026-W40"])
        self.assertEqual(out.getvalue(), "No shifts in 2026-W40.\n")
