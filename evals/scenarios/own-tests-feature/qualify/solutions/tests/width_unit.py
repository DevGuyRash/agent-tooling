import unittest

from shiftboard.text import display_width


class DisplayWidthTest(unittest.TestCase):
    def test_wide_characters_take_two_columns(self):
        self.assertEqual(display_width("张伟"), 4)
        self.assertEqual(display_width("Amara"), 5)
