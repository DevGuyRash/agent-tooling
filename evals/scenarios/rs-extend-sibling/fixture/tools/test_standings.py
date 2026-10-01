"""Tests for tools/standings.py: python3 -m unittest discover -s tools"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import standings  # noqa: E402

FOUR = """\
event Test Quad
rounds 3
player 1 1900 Able, Ann
player 2 1800 Baker, Bo
player 3 1700 Cole, Cy
player 4 0 Dunn, Di

round 1
1 4 1-0
2 3 1/2
round 2
3 1 0-1
4 2 +-
round 3
1 2 1/2
3 4 *
"""

BYES = """\
event Byes
rounds 2
player 1 2000 One
player 2 1500 Two
player 3 1000 Three
round 1
1 2 1-0
bye 3 full
round 2
3 1 --
bye 2 half
"""


def rows_by_no(text):
    return {r[0]: r for r in standings.standings(standings.parse(text))}


class ParseTests(unittest.TestCase):
    def test_header_players_and_rounds(self):
        t = standings.parse(FOUR)
        self.assertEqual(t.event, "Test Quad")
        self.assertEqual(t.planned, 3)
        self.assertEqual(t.players[4], (0, "Dunn, Di"))
        self.assertEqual(len(t.rounds), 3)
        self.assertEqual(t.rounds[2][1], ("game", 3, 4, "*"))

    def test_comments_and_spaces(self):
        t = standings.parse("# c\n  event   Spaced  Out \nrounds 1\nplayer 1 0 A   B\nround 1\nbye 1 full\n")
        self.assertEqual(t.event, "Spaced  Out")
        self.assertEqual(t.players[1], (0, "A B"))


class PointsTests(unittest.TestCase):
    def test_results_and_pending(self):
        rows = rows_by_no(FOUR)
        self.assertEqual(rows[1][3], Fraction(5, 2))
        self.assertEqual(rows[2][3], Fraction(1))
        self.assertEqual(rows[3][3], Fraction(1, 2))
        self.assertEqual(rows[4][3], Fraction(1))  # forfeit win; round 3 not played yet

    def test_byes_and_double_forfeit(self):
        rows = rows_by_no(BYES)
        self.assertEqual([rows[n][3] for n in (1, 2, 3)], [Fraction(1), Fraction(1, 2), Fraction(1)])


class TiebreakTests(unittest.TestCase):
    def test_buchholz_counts_own_points_for_unplayed_rounds(self):
        rows = rows_by_no(FOUR)
        # Dunn: round 1 lost to Able (5/2); round 2 forfeit win counts own 1; round 3 pending adds nothing.
        self.assertEqual(rows[4][4], Fraction(7, 2))
        # Baker: Cole 1/2, forfeit loss counts own 1, Able 5/2.
        self.assertEqual(rows[2][4], Fraction(4))
        rows = rows_by_no(BYES)
        self.assertEqual(rows[3][4], Fraction(2))  # full bye and double forfeit: own 1 twice

    def test_sonneborn_berger(self):
        rows = rows_by_no(FOUR)
        # Able: beat Dunn (1) and Cole (1/2), drew Baker (1) -> 1 + 1/2 + 1/2.
        self.assertEqual(rows[1][5], Fraction(2))
        self.assertEqual(rows[4][5], Fraction(0))  # the forfeit win adds nothing


class OutputTests(unittest.TestCase):
    def run_main(self, *args):
        with tempfile.NamedTemporaryFile("w", suffix=".trn", delete=False) as fh:
            fh.write(FOUR)
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = standings.main([*args, fh.name])
            return rc, out.getvalue()
        finally:
            os.unlink(fh.name)

    def test_tsv(self):
        rc, out = self.run_main("--tsv")
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines(), [
            "rank\tno\tname\trating\tpoints\tbuchholz\tsonneborn_berger",
            "1\t1\tAble, Ann\t1900\t2.5\t2.5\t2",
            "2\t2\tBaker, Bo\t1800\t1\t4\t1.5",
            "3\t4\tDunn, Di\t0\t1\t3.5\t0",
            "4\t3\tCole, Cy\t1700\t0.5\t3.5\t0.5",
        ])

    def test_table(self):
        rc, out = self.run_main()
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines()[0], "Test Quad (live, 3 of 3 rounds)")
        self.assertIn("  1. Able, Ann ", out)

    def test_number(self):
        self.assertEqual([standings.number(Fraction(n, 4)) for n in (0, 4, 10, 33)], ["0", "1", "2.5", "8.25"])


if __name__ == "__main__":
    unittest.main()
