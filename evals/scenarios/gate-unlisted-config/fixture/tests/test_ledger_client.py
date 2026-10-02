import unittest

from reports.ledger_client import Account, Balance, LedgerClient
from tests.fakes import FakeTransport


class LedgerClientTest(unittest.TestCase):
    def test_get_account(self):
        t = FakeTransport({"/v2/accounts/ACC-7": {"id": "ACC-7", "name": "Acme GmbH", "currency": "EUR", "status": "active"}})
        self.assertEqual(LedgerClient(t).get_account("ACC-7"), Account("ACC-7", "Acme GmbH", "EUR"))
        self.assertEqual(t.paths, ["/v2/accounts/ACC-7"])

    def test_get_balance(self):
        t = FakeTransport({"/v2/accounts/ACC-7/balance": {
            "account_id": "ACC-7",
            "available": {"amount": "1520.40", "currency": "EUR"},
            "pending": {"amount": "-12.05", "currency": "EUR"},
            "as_of": "2026-09-30T23:00:00Z"}})
        self.assertEqual(LedgerClient(t).get_balance("ACC-7"), Balance("ACC-7", 152040, -1205, "EUR"))
        self.assertEqual(t.paths, ["/v2/accounts/ACC-7/balance"])


if __name__ == "__main__":
    unittest.main()
