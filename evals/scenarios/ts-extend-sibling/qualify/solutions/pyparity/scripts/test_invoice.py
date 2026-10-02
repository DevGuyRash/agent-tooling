"""Tests for invoice.py. Run: python3 -m unittest discover -s scripts"""
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import invoice  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "invoice.py"

RATES = """\
# test rate card
[acme]
name = Acme Outdoor GmbH
currency = EUR
rate = 120
rate.site = 118.50
increment = 15
minimum = 30
tax = 19

[north]
  name   =   North Ferry Co. = boats
currency = NOK
rate = 80.05
"""

SHEET = """\
2026-09-01  09:00-09:10  acme/site   ten minutes
2026-09-01  40m          acme/site   forty
2026-09-02  1h           acme/brand  an hour
2026-09-02  6m           north/web   six minutes
2026-10-01  2h           acme/site   next month
"""


class Files:
    def __init__(self):
        self.dir = tempfile.TemporaryDirectory()

    def write(self, name, text):
        path = Path(self.dir.name) / name
        path.write_text(text)
        return str(path)


class RateCard(unittest.TestCase):
    def setUp(self):
        self.files = Files()
        self.addCleanup(self.files.dir.cleanup)

    def test_reads_clients(self):
        clients = invoice.read_rates(self.files.write("rates.txt", RATES))
        self.assertEqual(sorted(clients), ["acme", "north"])
        acme = clients["acme"]
        self.assertEqual((acme["rate"], acme["increment"], acme["minimum"], acme["tax"]),
                         (Decimal("120"), 15, 30, Decimal("19")))
        self.assertEqual(acme["projects"], {"site": Decimal("118.50")})
        north = clients["north"]
        self.assertEqual(north["name"], "North Ferry Co. = boats")
        self.assertEqual((north["increment"], north["minimum"], north["tax"]), (1, 0, Decimal(0)))

    def test_errors_name_the_line(self):
        cases = {
            "rate = 1\n[a]\nname = A\ncurrency = EUR\n": 1,
            "[a]\nname = A\ncurrency = EUR\nrate = 1\nrat = 2\n": 5,
            "[a]\nname = A\ncurrency = EUR\nrate = 1\nrate = 2\n": 5,
            "[a]\nname = A\ncurrency = eur\nrate = 1\n": 3,
            "[a]\nname = A\ncurrency = EUR\nrate = 1.005\n": 4,
            "[a]\nname = A\ncurrency = EUR\nrate = 1\nincrement = 0\n": 5,
            "[a]\nname = A\ncurrency = EUR\nrate = 1\ntax = 100.01\n": 5,
            "\n[a]\nname = A\nrate = 1\n[b]\nname = B\ncurrency = EUR\nrate = 1\n": 2,
            "[a]\nname = A\ncurrency = EUR\nrate = 1\n[a]\n": 5,
            "[a]\nname = A\ncurrency EUR\n": 3,
            "[A]\nname = A\n": 1,
        }
        for text, line in cases.items():
            path = self.files.write("bad.txt", text)
            with self.assertRaises(invoice.InputError) as caught:
                invoice.read_rates(path)
            self.assertTrue(str(caught.exception).startswith(f"{path}:{line}: "), (text, str(caught.exception)))


class Billing(unittest.TestCase):
    def setUp(self):
        self.files = Files()
        self.addCleanup(self.files.dir.cleanup)
        self.clients = invoice.read_rates(self.files.write("rates.txt", RATES))
        self.entries = invoice.read_timesheet(self.files.write("sheet.txt", SHEET))

    def test_rounding_each_entry(self):
        acme = self.clients["acme"]
        self.assertEqual([invoice.billed_minutes(m, acme) for m in (1, 10, 30, 31, 40, 45, 46)],
                         [30, 30, 30, 45, 45, 45, 60])

    def test_project_rates_and_tax(self):
        inv = invoice.invoice("acme", self.clients["acme"], self.entries, "2026-09")
        self.assertEqual([(p["project"], p["entries"], p["minutes"], p["billed_minutes"], p["rate"], p["amount"])
                          for p in inv["projects"]],
                         [("acme/brand", 1, 60, 60, "120.00", "120.00"), ("acme/site", 2, 50, 75, "118.50", "148.13")])
        self.assertEqual((inv["subtotal"], inv["tax_percent"], inv["tax"], inv["total"]),
                         ("268.13", "19", "50.94", "319.07"))

    def test_half_cents_round_up(self):
        inv = invoice.invoice("north", self.clients["north"], self.entries)
        self.assertEqual(inv["projects"][0]["amount"], "8.01")  # 6 minutes at 80.05 is 8.005
        self.assertEqual((inv["tax_percent"], inv["tax"], inv["total"]), ("0", "0.00", "8.01"))


class CommandLine(unittest.TestCase):
    def test_json(self):
        files = Files()
        self.addCleanup(files.dir.cleanup)
        rates, sheet = files.write("rates.txt", RATES), files.write("sheet.txt", SHEET)
        r = subprocess.run([sys.executable, str(SCRIPT), "--rates", rates, "--client", "acme", "--month", "2026-10",
                            "--json", sheet], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        inv = json.loads(r.stdout)
        self.assertEqual([p["project"] for p in inv["projects"]], ["acme/site"])
        self.assertEqual(inv["total"], "282.03")  # 2h at 118.50 is 237.00, plus 19%

    def test_unknown_client(self):
        files = Files()
        self.addCleanup(files.dir.cleanup)
        rates, sheet = files.write("rates.txt", RATES), files.write("sheet.txt", SHEET)
        r = subprocess.run([sys.executable, str(SCRIPT), "--rates", rates, "--client", "bolt", sheet],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn('no client "bolt"', r.stderr)
        self.assertEqual(r.stdout, "")


class HoursInvoiceParity(unittest.TestCase):
    """hours invoice and this script agree on a month with no +nobill entries (docs/invoice.md: compare the two)."""

    def test_same_totals_as_hours_invoice(self):
        import shutil
        import subprocess
        from pathlib import Path
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        root = Path(__file__).resolve().parent.parent
        sheet = root / "test" / "data" / "sample.txt"
        args = ["--client", "acme", "--rates", str(root / "rates.txt"), "--month", "2026-03", str(sheet)]
        hours = subprocess.run([node, str(root / "bin" / "hours.ts"), "invoice", *args], capture_output=True, text=True, check=True)
        mine = subprocess.run([sys.executable, str(root / "scripts" / "invoice.py"), "--json", *args], capture_output=True, text=True, check=True)
        total = json.loads(mine.stdout)["total"]
        self.assertIn(total, hours.stdout)


if __name__ == "__main__":
    unittest.main()
