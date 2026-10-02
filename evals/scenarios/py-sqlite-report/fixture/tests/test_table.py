import unittest

from dockops.table import render


class RenderTest(unittest.TestCase):
    def test_widths_alignment_and_no_trailing_spaces(self):
        lines = render(("code", "station", "n"), [("HB1", "Ferry Terminal", 7), ("UNI12", "Dry Dock", 12)], "llr")
        self.assertEqual(lines, ["code   station          n",
                                 "HB1    Ferry Terminal   7",
                                 "UNI12  Dry Dock        12"])

    def test_header_only(self):
        self.assertEqual(render(("a", "b"), [], "lr"), ["a  b"])
