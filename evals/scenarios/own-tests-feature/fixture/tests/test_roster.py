import os
import tempfile
import unittest
from datetime import date, time

from shiftboard.roster import RosterError, load


class RosterTest(unittest.TestCase):
    def write(self, text):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_reads_shifts_in_file_order(self):
        path = self.write("date,start,end,station,volunteer\n"
                          "2026-09-15,17:00,20:00,Serving,Ines Duarte\n"
                          "2026-09-14,09:00,12:00,Prep,Amara Okafor\n")
        shifts = load(path)
        self.assertEqual([s.volunteer for s in shifts], ["Ines Duarte", "Amara Okafor"])
        self.assertEqual(shifts[1].date, date(2026, 9, 14))
        self.assertEqual(shifts[1].start, time(9, 0))
        self.assertEqual(shifts[0].hours, 3.0)

    def test_skips_blank_lines_and_trims_cells(self):
        path = self.write("date,start,end,station,volunteer\n\n 2026-09-14 , 09:00 ,12:30, Prep , Amara Okafor \n")
        [shift] = load(path)
        self.assertEqual((shift.station, shift.volunteer, shift.hours), ("Prep", "Amara Okafor", 3.5))

    def test_errors_name_file_and_line(self):
        cases = [
            ("date,start,end,station\n", 1, "header must be date,start,end,station,volunteer"),
            ("date,start,end,station,volunteer\n2026-09-14,9:00,12:00,Prep,A\n", 2, "bad time '9:00'"),
            ("date,start,end,station,volunteer\n2026-02-30,09:00,12:00,Prep,A\n", 2, "bad date '2026-02-30'"),
            ("date,start,end,station,volunteer\n\n2026-09-14,12:00,09:00,Prep,A\n", 3, "shift ends before it starts"),
            ("date,start,end,station,volunteer\n2026-09-14,09:00,12:00,Prep\n", 2, "expected 5 fields, found 4"),
            ("date,start,end,station,volunteer\n2026-09-14,09:00,12:00,,A\n", 2, "no station"),
        ]
        for text, line, message in cases:
            with self.subTest(message=message):
                path = self.write(text)
                with self.assertRaises(RosterError) as caught:
                    load(path)
                self.assertEqual(str(caught.exception), f"{path}:{line}: {message}")
