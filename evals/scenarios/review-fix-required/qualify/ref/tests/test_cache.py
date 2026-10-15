import unittest

from stampcard.directory import Card, Directory


class LookupOnceTest(unittest.TestCase):
    def test_each_card_id_is_looked_up_once(self):  # R4
        asked = []

        def lookup(card_id):
            asked.append(card_id)
            return Card(card_id, "n", 0) if card_id == "C-001" else None

        directory = Directory(lookup)
        for _ in range(3):
            directory.get("C-001")
            self.assertRaises(KeyError, directory.get, "C-404")
        self.assertEqual(sorted(asked), ["C-001", "C-404"])


if __name__ == "__main__":
    unittest.main()
