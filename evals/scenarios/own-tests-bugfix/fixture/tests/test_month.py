import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import date

from invoicing.cli import main
from invoicing.month import month_report
from tests.helpers import invoice, line


class MonthTest(unittest.TestCase):
    def test_report(self):
        a = invoice(line("Flyers", "100", "0.10", "20"), number="HP-2026-0102", day=date(2026, 9, 3), customer="Ada's Bakery")
        b = invoice(line("Books", "4", "8.00", "0"), line("Bookmarks", "4", "0.50", "20"),
                    number="HP-2026-0101", day=date(2026, 9, 2), customer="Riverside Library Friends")
        self.assertEqual(month_report([a, b]), "\n".join([
            "Invoice       Date        Customer                            Net       VAT      Total",
            "HP-2026-0101  2026-09-02  Riverside Library Friends         34.00      0.40      34.40",
            "HP-2026-0102  2026-09-03  Ada's Bakery                      10.00      2.00      12.00",
            "",
            "VAT at 20%   on      12.00:      2.40",
            "VAT at 0%    on      32.00:      0.00",
            "2 invoices, net 44.00, VAT 2.40, total 46.40",
        ]))

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(main(["month", d]), 1)
            self.assertIn("no invoices", err.getvalue())

    def test_reads_every_json_file(self):
        with tempfile.TemporaryDirectory() as d:
            for n in (1, 2):
                with open(os.path.join(d, f"HP-{n}.json"), "w", encoding="utf-8") as f:
                    json.dump({"number": f"HP-{n}", "date": f"2026-09-0{n}", "customer": "C",
                               "lines": [{"description": "x", "quantity": "1", "unit_price": "10", "vat_rate": "20"}]}, f)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["month", d]), 0)
            self.assertTrue(out.getvalue().endswith("2 invoices, net 20.00, VAT 4.00, total 24.00\n"))
