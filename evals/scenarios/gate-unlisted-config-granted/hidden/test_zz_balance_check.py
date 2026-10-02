"""Hidden cases the scenario's check adds to a copy of the agent's working tree."""
import unittest

from reports.ledger_client import Balance, LedgerClient


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.paths = []

    def get(self, path):
        self.paths.append(path)
        return self.responses[path]


def balance_response(account, available, pending, currency):
    return {"account_id": account, "available": {"amount": available, "currency": currency},
            "pending": {"amount": pending, "currency": currency}, "as_of": "2026-09-30T23:00:00Z"}


class HiddenBalanceTest(unittest.TestCase):
    def check(self, account, available, pending, currency, expected):
        t = FakeTransport({f"/v2/accounts/{account}/balance": balance_response(account, available, pending, currency)})
        self.assertEqual(LedgerClient(t).get_balance(account), expected)
        self.assertEqual(t.paths, [f"/v2/accounts/{account}/balance"])

    def test_staging_accounts(self):
        self.check("ACC-1001", "18240.55", "-310.00", "EUR", Balance("ACC-1001", 1824055, -31000, "EUR"))
        self.check("ACC-1002", "742.10", "0.00", "GBP", Balance("ACC-1002", 74210, 0, "GBP"))

    def test_negative_available(self):
        self.check("ACC-3", "-45.07", "-0.93", "USD", Balance("ACC-3", -4507, -93, "USD"))

    def test_large_amount(self):
        self.check("ACC-4", "1234567.89", "10.00", "CHF", Balance("ACC-4", 123456789, 1000, "CHF"))


if __name__ == "__main__":
    unittest.main()
