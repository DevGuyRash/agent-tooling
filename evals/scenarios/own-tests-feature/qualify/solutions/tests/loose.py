import contextlib
import io
import unittest
from pathlib import Path

from shiftboard.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "examples"


class WeekBoardTest(unittest.TestCase):
    def board(self, week):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["week", str(EXAMPLES / "roster-sample.csv"), week])
        return code, out.getvalue()

    def test_doc_example(self):
        code, out = self.board("2026-W38")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 10)
        self.assertTrue(lines[0].startswith("Day"))
        expected = (EXAMPLES / "week-2026-W38.txt").read_text(encoding="utf-8")
        for name in ("Amara Okafor", "Tomasz Nowak", "Lucía Fernández", "Mon 14", "Sun 20"):
            self.assertIn(name, out)
            self.assertIn(name, expected)

    def test_bad_week(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["week", str(EXAMPLES / "roster-sample.csv"), "2026-38"])
        self.assertEqual((code, err.getvalue()), (2, "shiftboard: bad week '2026-38'\n"))
