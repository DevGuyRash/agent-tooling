import json
import os
import tempfile
import unittest
from decimal import Decimal

from invoicing.load import InvoiceError, load


class LoadTest(unittest.TestCase):
    def write(self, data):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        self.addCleanup(os.remove, path)
        return path

    def test_loads_lines_as_decimals(self):
        path = self.write({"number": "HP-1", "date": "2026-09-01", "customer": "C",
                           "lines": [{"description": "x", "quantity": "2", "unit_price": "1.10", "vat_rate": "20"}]})
        inv = load(path)
        self.assertEqual(inv.lines[0].unit_price, Decimal("1.10"))
        self.assertEqual(inv.lines[0].net, Decimal("2.20"))

    def test_errors(self):
        good_line = {"description": "x", "quantity": "1", "unit_price": "1", "vat_rate": "20"}
        cases = [
            ("{", "not JSON"),
            ({"number": "1", "date": "2026-09-01", "customer": "C"}, "missing 'lines'"),
            ({"number": "1", "date": "2026-13-01", "customer": "C", "lines": [good_line]}, "bad date"),
            ({"number": "1", "date": "2026-09-01", "customer": "C", "lines": []}, "at least one line"),
            ({"number": "1", "date": "2026-09-01", "customer": "C", "lines": [dict(good_line, unit_price=1.5)]},
             "line 1 unit_price must be a string"),
        ]
        for data, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(InvoiceError) as caught:
                    load(self.write(data))
                self.assertIn(message, str(caught.exception))
