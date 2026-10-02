import unittest

from reports.balances_report import balance_rows, format_rows
from reports.ledger_client import LedgerClient
from tests.fakes import FakeTransport


class BalancesReportTest(unittest.TestCase):
    def test_rows(self):
        t = FakeTransport({
            "/v2/accounts/ACC-7": {"id": "ACC-7", "name": "Acme GmbH", "currency": "EUR", "status": "active"},
            "/v2/accounts/ACC-7/balance": {"account_id": "ACC-7", "available": {"amount": "99.90", "currency": "EUR"},
                                           "pending": {"amount": "0.00", "currency": "EUR"}, "as_of": "2026-09-30T23:00:00Z"},
        })
        rows = balance_rows(LedgerClient(t), ["ACC-7"])
        self.assertEqual(rows, [{"account": "ACC-7", "name": "Acme GmbH", "currency": "EUR", "available": 9990, "pending": 0}])
        self.assertIn("available        99.90", format_rows(rows))


if __name__ == "__main__":
    unittest.main()
