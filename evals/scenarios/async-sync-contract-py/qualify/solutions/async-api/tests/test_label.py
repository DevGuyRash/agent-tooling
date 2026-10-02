import asyncio
import unittest

from shelftag import Item, LabelError
from shelftag import label_text as _label_text


def label_text(*args, **kwargs):
    return asyncio.run(_label_text(*args, **kwargs))


class LabelTest(unittest.TestCase):
    def test_full_label(self):
        item = Item("Bio Bergkäse", 490, net_grams=200, origin="Schweiz")
        self.assertEqual(label_text(item), "Bio Bergkäse\nCHF 4.90\nCHF 2.45 / 100 g\nHerkunft: Schweiz")

    def test_price_only(self):
        self.assertEqual(label_text(Item("Zitronen", 65)), "Zitronen\nCHF 0.65")

    def test_unit_price_per_kg(self):
        self.assertEqual(label_text(Item("Haferdrink", 225, net_grams=1000)), "Haferdrink\nCHF 2.25\nCHF 2.25 / kg")
        self.assertEqual(label_text(Item("Kartoffeln", 495, net_grams=2500)), "Kartoffeln\nCHF 4.95\nCHF 1.98 / kg")

    def test_unit_price_rounds_half_up(self):
        # 3.60 for 500 g is 0.72 per 100 g; 1.25 for 250 g is exactly 0.50; 0.99 for 200 g is 0.495 -> 0.50
        self.assertEqual(label_text(Item("Ruchbrot", 360, net_grams=500)).splitlines()[2], "CHF 0.72 / 100 g")
        self.assertEqual(label_text(Item("Hefe", 125, net_grams=250)).splitlines()[2], "CHF 0.50 / 100 g")
        self.assertEqual(label_text(Item("Salz", 99, net_grams=200)).splitlines()[2], "CHF 0.50 / 100 g")

    def test_long_name_cut(self):
        text = label_text(Item("Basler Läckerli Original im Geschenkkarton", 1280), width=20)
        self.assertEqual(text.splitlines()[0], "Basler Läckerli Ori…")

    def test_origin_cut(self):
        text = label_text(Item("Tee", 590, origin="Vereinigtes Königreich"), width=20)
        self.assertEqual(text.splitlines()[-1], "Herkunft: Vereinigt…")

    def test_width_too_small(self):
        with self.assertRaises(LabelError):
            label_text(Item("Tee", 590), width=15)

    def test_negative_price(self):
        with self.assertRaises(LabelError):
            label_text(Item("Tee", -1))


if __name__ == "__main__":
    unittest.main()
