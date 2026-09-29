import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

from billing.models import Invoice, InvoiceLine
from billing.store import InvoiceStore


def sample(number, issued_on=date(2026, 9, 3)):
    line = InvoiceLine("PAP-LTR", "Copy paper", D("2"), D("6.50"), D("13.00"))
    return Invoice(number, "SO-7", "C-7", issued_on, [line], D("13.00"), D("0.00"), D("0.00"), D("13.00"), "text\n")


class InvoiceStoreTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def test_numbers_continue_across_store_instances(self):
        self.assertEqual(InvoiceStore(self.dir).next_number(), "INV-000001")
        self.assertEqual(InvoiceStore(self.dir).next_number(), "INV-000002")

    def test_save_and_load(self):
        store = InvoiceStore(self.dir)
        store.save(sample("INV-000009"))
        self.assertEqual(store.load("INV-000009"), sample("INV-000009"))

    def test_all_in_number_order(self):
        store = InvoiceStore(self.dir)
        for number in ("INV-000002", "INV-000001"):
            store.save(sample(number))
        self.assertEqual([inv.number for inv in store.all()], ["INV-000001", "INV-000002"])


if __name__ == "__main__":
    unittest.main()
