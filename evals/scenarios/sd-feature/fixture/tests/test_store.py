import unittest

from inventory import Inventory


class InventoryTest(unittest.TestCase):
    def test_add_and_count(self):
        inv = Inventory()
        inv.add("bolt", 3)
        self.assertEqual(inv.count("bolt"), 3)

    def test_remove_more_than_stock(self):
        inv = Inventory()
        inv.add("nut")
        with self.assertRaises(ValueError):
            inv.remove("nut", 2)


if __name__ == "__main__":
    unittest.main()
