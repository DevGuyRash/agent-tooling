import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

from billing.invoice import generate_invoice
from billing.models import Customer, LineItem, Order
from billing.store import InvoiceStore

ISSUED = date(2026, 9, 1)
PAPER = LineItem("PAP-LTR", "Copy paper, letter, 500 sheets", D("4"), D("5.00"))
TONER = LineItem("TON-12", "Toner cartridge, black", D("1"), D("20.00"))
SETUP = LineItem("SVC-SETUP", "Printer setup (service)", D("1"), D("15.00"), taxable=False)

PRINTED = """\
Acme Office Supply
400 Harbor Way, Portland, OR 97209

INVOICE INV-000001                                     Issued 2026-09-01
Order SO-2291
Bill to: Rose City Pediatrics (C-118)
------------------------------------------------------------------------
PAP-LTR    Copy paper, letter, 500 sheets      4 x      5.00       20.00
TON-12     Toner cartridge, black              1 x     20.00       20.00
SVC-SETUP  Printer setup (service)             1 x     15.00       15.00 *
------------------------------------------------------------------------
                                                    Subtotal       55.00
                                          Silver discount 5%       -2.75
                                           Sales tax WA 6.5%        2.47
                                                       Total       54.72

* no sales tax on this line
"""


class GenerateInvoiceTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = InvoiceStore(tmp.name)
        self.texan = Customer("C-100", "Lone Star Dental", "TX")

    def invoice(self, customer, *lines, order_id="SO-1001"):
        return generate_invoice(Order(order_id, customer, list(lines)), self.store, ISSUED)

    def test_totals(self):
        inv = self.invoice(self.texan, PAPER, TONER)
        self.assertEqual([line.amount for line in inv.lines], [D("20.00"), D("20.00")])
        self.assertEqual(inv.subtotal, D("40.00"))
        self.assertEqual(inv.discount, D("0.00"))
        self.assertEqual(inv.tax, D("3.30"))
        self.assertEqual(inv.total, D("43.30"))

    def test_loyalty_discount_lowers_the_taxable_amount(self):
        gold = Customer("C-200", "Harbor Law LLP", "TX", tier="gold")
        inv = self.invoice(gold, LineItem("CHR-5", "Task chair", D("2"), D("100.00")))
        self.assertEqual(inv.subtotal, D("200.00"))
        self.assertEqual(inv.discount, D("20.00"))
        self.assertEqual(inv.tax, D("14.85"))  # 8.25% of 180.00
        self.assertEqual(inv.total, D("194.85"))

    def test_untaxed_lines(self):
        inv = self.invoice(self.texan, TONER, LineItem("SVC-SETUP", "Printer setup", D("1"), D("45.00"), taxable=False))
        self.assertEqual(inv.subtotal, D("65.00"))
        self.assertEqual(inv.tax, D("1.65"))
        self.assertEqual(inv.total, D("66.65"))

    def test_region_without_sales_tax(self):
        oregon = Customer("C-300", "Willamette Books", "OR")
        inv = self.invoice(oregon, LineItem("BIN-3", "Storage bin", D("3"), D("12.00")))
        self.assertEqual(inv.tax, D("0.00"))
        self.assertEqual(inv.total, D("36.00"))

    def test_printed_invoice(self):
        silver = Customer("C-118", "Rose City Pediatrics", "WA", tier="silver")
        inv = self.invoice(silver, PAPER, TONER, SETUP, order_id="SO-2291")
        self.assertEqual(inv.text, PRINTED)

    def test_invoice_numbers_follow_in_sequence(self):
        first = self.invoice(self.texan, PAPER)
        second = self.invoice(self.texan, TONER, order_id="SO-1002")
        self.assertEqual((first.number, second.number), ("INV-000001", "INV-000002"))

    def test_rejected_order_does_not_use_a_number(self):
        with self.assertRaises(ValueError):
            self.invoice(self.texan, LineItem("PAP-LTR", "Copy paper", D("0"), D("5.00")))
        self.assertEqual(self.invoice(self.texan, PAPER).number, "INV-000001")

    def test_order_without_lines_is_rejected(self):
        with self.assertRaises(ValueError):
            self.invoice(self.texan)

    def test_unknown_region_is_rejected(self):
        with self.assertRaises(ValueError):
            self.invoice(Customer("C-400", "Nowhere Inc", "ZZ"), PAPER)

    def test_invoice_is_saved(self):
        inv = self.invoice(self.texan, PAPER, SETUP)
        self.assertEqual(self.store.load(inv.number), inv)


if __name__ == "__main__":
    unittest.main()
