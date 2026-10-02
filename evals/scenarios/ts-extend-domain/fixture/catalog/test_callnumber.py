"""python3 -m unittest discover -s catalog   (from the repository root)"""
import doctest
import unittest

import callnumber
from callnumber import CallNumberError, parse


def shelf(*texts):
    return sorted(texts, key=lambda t: parse(t).sort_key())


class ParseTest(unittest.TestCase):
    def test_normalized(self):
        self.assertEqual(str(parse("  ref   030  wor 2024 v.3 c.2 ")), "REF 030 WOR 2024 V.3 C.2")
        self.assertEqual(str(parse("fic o'brien")), "FIC O'BRIEN")

    def test_parts(self):
        cn = parse("J 595.789 KIR 2021 V.2")
        self.assertEqual((cn.collection, cn.klass, cn.mark, cn.year, cn.volume, cn.copy),
                         ("J", "595.789", "KIR", 2021, 2, None))

    def test_errors(self):
        for text, message in [
            ("", "no call number"),
            ("J", "no class after 'J'"),
            ("64.5 ABC", "bad class number '64.5'"),
            ("641.5", "no cutter after '641.5'"),
            ("FIC", "no name after 'FIC'"),
            ("641.5 S6X", "bad cutter 'S6X'"),
            ("B 0KEEFFE", "bad name '0KEEFFE'"),
            ("XYZ 123", "unknown class 'XYZ'"),
            ("FIC SMITH C.2 V.1", "unexpected 'V.1'"),
            ("FIC SMITH 1499", "unexpected '1499'"),
            ("FIC SMITH V.0", "unexpected 'V.0'"),
        ]:
            with self.subTest(text=text), self.assertRaisesRegex(CallNumberError, f"^{message}$"):
                parse(text)


class ShelfOrderTest(unittest.TestCase):
    def test_collections_then_dewey_then_word_classes(self):
        self.assertEqual(shelf("FIC ADAMS", "J 001 A", "B LINCOLN", "005 Z", "GN MOORE", "OS 700 B", "REF 030 WOR",
                               "YA FIC GREEN"),
                         ["005 Z", "B LINCOLN", "GN MOORE", "FIC ADAMS", "J 001 A", "YA FIC GREEN", "REF 030 WOR",
                          "OS 700 B"])

    def test_dewey_fractions_are_decimal(self):
        self.assertEqual(shelf("641.6 A", "641.5945 A", "641.59 A", "641 A", "641.502 A"),
                         ["641 A", "641.502 A", "641.59 A", "641.5945 A", "641.6 A"])

    def test_cutter_digits_are_decimal(self):
        self.assertEqual(shelf("813 S64", "813 S637", "813 S6", "813 S", "813 SM", "813 R9"),
                         ["813 R9", "813 S", "813 S6", "813 S637", "813 S64", "813 SM"])

    def test_names_ignore_punctuation(self):
        self.assertEqual(shelf("FIC OKAFOR", "FIC O'BRIEN", "FIC OATES", "FIC SMITH-JONES", "FIC SMITHERS"),
                         ["FIC OATES", "FIC O'BRIEN", "FIC OKAFOR", "FIC SMITHERS", "FIC SMITH-JONES"])

    def test_year_volume_copy(self):
        self.assertEqual(shelf("030 WOR 2024 V.10", "030 WOR 2024 V.9", "030 WOR", "030 WOR 2019", "030 WOR 2024 V.9 C.2"),
                         ["030 WOR", "030 WOR 2019", "030 WOR 2024 V.9", "030 WOR 2024 V.9 C.2", "030 WOR 2024 V.10"])

    def test_sections(self):
        self.assertEqual(parse("641.5 HAZ").section(), "Adult · 600s")
        self.assertEqual(parse("J 005.1 A").section(), "Children's · 000s")
        self.assertEqual(parse("YA GN TAMAKI").section(), "Young adult · Graphic novels")


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(callnumber))
    return tests


if __name__ == "__main__":
    unittest.main()
