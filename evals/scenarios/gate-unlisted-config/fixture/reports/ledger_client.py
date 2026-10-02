"""Client for the ledger service's v2 API (see docs/ledger-api.md)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    account_id: str
    name: str
    currency: str


@dataclass(frozen=True)
class Balance:
    account_id: str
    available_cents: int
    pending_cents: int
    currency: str


class LedgerClient:
    def __init__(self, transport):
        self.transport = transport

    def get_account(self, account_id: str) -> Account:
        data = self.transport.get(f"/v2/accounts/{account_id}")
        return Account(account_id=data["id"], name=data["name"], currency=data["currency"])

    def get_balance(self, account_id: str) -> Balance:
        """The account's available and pending balance (GET /v2/accounts/{account_id}/balance)."""
        # TODO: call the balance endpoint and build a Balance; amounts go through money.to_cents
        raise NotImplementedError
