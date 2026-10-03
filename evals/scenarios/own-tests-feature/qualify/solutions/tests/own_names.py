import subprocess
import sys
import unittest
from pathlib import Path

from shiftboard.widths import cell_width, pad

ROOT = Path(__file__).resolve().parent.parent


class KioskTest(unittest.TestCase):
    def test_cell_width(self):
        self.assertEqual(cell_width("陈美玲"), 6)
        self.assertEqual(pad("王芳", 6), "王芳  ")

    def test_doc_example_through_the_command(self):
        p = subprocess.run([sys.executable, "-m", "shiftboard", "week", "docs/examples/roster-sample.csv", "2026-W38"],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, (ROOT / "docs/examples/week-2026-W38.txt").read_text(encoding="utf-8"))
