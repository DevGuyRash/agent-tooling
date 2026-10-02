import unittest

from ledgerkit.numbering import next_credit_note_number


class NumberingTest(unittest.TestCase):
    def test_first_number(self):
        self.assertEqual(next_credit_note_number(None), "CN-000001")

    def test_increments(self):
        self.assertEqual(next_credit_note_number("CN-000041"), "CN-000042")

    def test_rejects_other_formats(self):
        with self.assertRaises(ValueError):
            next_credit_note_number("INV-1042")


if __name__ == "__main__":
    unittest.main()
