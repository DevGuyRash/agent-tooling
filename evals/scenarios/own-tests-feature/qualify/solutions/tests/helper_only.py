import contextlib
import io
import os
import tempfile
import unittest

from shiftboard.cli import main
from shiftboard.widths import cell_width

ROSTER = """date,start,end,station,volunteer
2026-09-14,09:00,12:00,Prep,Amara Okafor
2026-09-16,17:00,20:00,Serving,Ines Duarte
"""


class WidthTest(unittest.TestCase):
    def test_wide_characters_take_two_columns(self):
        self.assertEqual(cell_width("张伟"), 4)
        self.assertEqual(cell_width("김민준"), 6)
        self.assertEqual(cell_width("Lucía"), 5)

    def test_board(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(ROSTER)
        self.addCleanup(os.remove, path)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["week", path, "2026-W38"])
        self.assertEqual(out.getvalue(), "Day     Time         Volunteer     Station\n"
                                         "------  -----------  ------------  -------\n"
                                         "Mon 14  09:00-12:00  Amara Okafor  Prep\n"
                                         "Wed 16  17:00-20:00  Ines Duarte   Serving\n")
