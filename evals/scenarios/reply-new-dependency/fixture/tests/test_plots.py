import datetime
import os
import tempfile
import unittest

from plotkeeper.plots import HEADER, PlotsError, plot_order, read_plots


def write(text):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


class ReadPlotsTests(unittest.TestCase):
    def tearDown(self):
        for path in getattr(self, "paths", []):
            os.unlink(path)

    def register(self, *rows):
        path = write(HEADER + "\n" + "".join(r + "\n" for r in rows))
        self.paths = getattr(self, "paths", []) + [path]
        return path

    def test_reads_the_shipped_register(self):
        plots = read_plots("data/plots.csv")
        self.assertEqual(len(plots), 29)
        a1 = plots[0]
        self.assertEqual((a1.plot, a1.size_m2, a1.kind, a1.holder), ("A1", 250, "full", "Margaret Hollis"))
        self.assertEqual(a1.start, datetime.date(2011, 4, 2))
        self.assertFalse(a1.concession)
        self.assertEqual(a1.water, "Y")

    def test_vacant_plot(self):
        (p,) = read_plots(self.register("A6,250,full,,,,Y"))
        self.assertTrue(p.vacant)
        self.assertIsNone(p.start)

    def test_trims_fields_and_skips_blank_lines(self):
        (p,) = read_plots(self.register("", " B3 , 125 , half , Aisha Bello , 2024-02-28 , Y , T ", "   "))
        self.assertEqual((p.plot, p.holder, p.concession, p.water), ("B3", "Aisha Bello", True, "T"))

    def test_plot_order_is_numeric_within_a_site(self):
        plots = read_plots(self.register("A10,1,bed,X,2020-01-01,,", "B1,1,bed,Y,2020-01-01,,", "A2,1,bed,Z,2020-01-01,,"))
        self.assertEqual([p.plot for p in sorted(plots, key=plot_order)], ["A2", "A10", "B1"])

    def test_errors_name_the_line(self):
        cases = [
            ("A1,250,full,Ann,2020-01-01,", "line 2: expected 7 fields, found 6"),
            ("a1,250,full,Ann,2020-01-01,,", 'line 2: bad plot id "a1"'),
            ("A1,0,full,Ann,2020-01-01,,", 'line 2: bad size "0"'),
            ("A1,250,orchard,Ann,2020-01-01,,", 'line 2: unknown kind "orchard"'),
            ("A1,250,full,Ann,2020-02-30,,", 'line 2: bad start date "2020-02-30"'),
            ("A1,250,full,Ann,2020-01-01,yes,", 'line 2: bad concession flag "yes"'),
            ("A1,250,full,Ann,2020-01-01,,N", 'line 2: bad water flag "N"'),
        ]
        for row, message in cases:
            with self.subTest(row=row):
                path = self.register(row)
                with self.assertRaises(PlotsError) as cm:
                    read_plots(path)
                self.assertEqual(str(cm.exception), f"{path} {message}")

    def test_duplicate_plot(self):
        path = self.register("A1,250,full,Ann,2020-01-01,,", "A1,125,half,Bob,2021-01-01,,")
        with self.assertRaisesRegex(PlotsError, "line 3: plot A1 listed twice"):
            read_plots(path)

    def test_header_is_required(self):
        path = write("plot,size,kind\n")
        self.paths = [path]
        with self.assertRaisesRegex(PlotsError, "line 1: expected header"):
            read_plots(path)

    def test_missing_file(self):
        with self.assertRaisesRegex(PlotsError, "cannot read nowhere.csv"):
            read_plots("nowhere.csv")


if __name__ == "__main__":
    unittest.main()
