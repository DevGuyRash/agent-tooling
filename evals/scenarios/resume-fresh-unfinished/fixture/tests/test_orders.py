import unittest

from orders import DuplicateOrderError, import_rows


class ImportRowsTest(unittest.TestCase):
    def test_import_accepts_unique_rows(self):
        rows = [{"order_id": "A1", "amount": 10}, {"order_id": "A2", "amount": 20}]
        self.assertEqual(len(import_rows(rows)), 2)

    def test_duplicate_batch_raises(self):
        rows = [{"order_id": "A1", "amount": 10}, {"order_id": "A1", "amount": 5}]
        with self.assertRaises(DuplicateOrderError):
            import_rows(rows)


if __name__ == "__main__":
    unittest.main()
