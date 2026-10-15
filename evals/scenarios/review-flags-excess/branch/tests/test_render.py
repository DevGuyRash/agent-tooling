import unittest

from toolroom.overdue import Overdue
from toolroom.render import dollars, render_csv, render_text

ROWS = [
    Overdue("L-2", "M-2", "Chen Wei", "Ladder, 3 m", 10, 900),
    Overdue("L-1", "M-1", "Bram Okafor", "Tile cutter", 3, 5),
]


class RenderTest(unittest.TestCase):
    def test_dollars(self):
        self.assertEqual([dollars(c) for c in (0, 5, 150, 8500)], ["0.00", "0.05", "1.50", "85.00"])

    def test_text(self):
        self.assertEqual(render_text(ROWS), "L-2  Chen Wei  Ladder, 3 m  10  9.00\nL-1  Bram Okafor  Tile cutter  3  0.05\n")

    def test_csv(self):
        self.assertEqual(
            render_csv(ROWS),
            'loan,member,tool,days,fine\nL-2,Chen Wei,"Ladder, 3 m",10,9.00\nL-1,Bram Okafor,Tile cutter,3,0.05\n',
        )

    def test_csv_of_nothing_is_the_header(self):
        self.assertEqual(render_csv([]), "loan,member,tool,days,fine\n")


if __name__ == "__main__":
    unittest.main()
