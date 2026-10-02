# ledger API v2: consumer notes

Owned by ledger-team. Reached through the mesh as the `ledger` service. Amounts are decimal strings with
two places, in the account's currency.

## GET /v2/accounts/{account_id}

```json
{"id": "ACC-1001", "name": "Northwind Traders", "currency": "EUR", "status": "active"}
```

## GET /v2/accounts/{account_id}/balance

```json
{"account_id": "ACC-1001",
 "available": {"amount": "18240.55", "currency": "EUR"},
 "pending": {"amount": "-310.00", "currency": "EUR"},
 "as_of": "2026-09-30T23:00:00Z"}
```

`available` and `pending` are always in the account's currency. `pending` is negative when outgoing
payments are waiting to settle.

## Errors

404 for an unknown account. The body is `{"error": "..."}`.
