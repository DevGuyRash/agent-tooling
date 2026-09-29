import datetime


class Ledger:
    def __init__(self):
        self.entries = []

    def post(self, debit, credit, amount_cents, memo=""):
        if amount_cents <= 0:
            raise ValueError("amount must be positive")
        self.entries.append((datetime.datetime.utcnow(), debit, credit, amount_cents, memo))

    def balance(self, account):
        return sum(a if d == account else -a if c == account else 0 for _, d, c, a, _ in self.entries)
