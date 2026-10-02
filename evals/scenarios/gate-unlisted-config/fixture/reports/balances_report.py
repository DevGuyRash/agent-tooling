"""Month-end balances report for finance."""
from .money import from_cents


def balance_rows(client, account_ids):
    rows = []
    for account_id in account_ids:
        account = client.get_account(account_id)
        balance = client.get_balance(account_id)
        rows.append({"account": account.account_id, "name": account.name, "currency": balance.currency,
                     "available": balance.available_cents, "pending": balance.pending_cents})
    return rows


def format_rows(rows) -> str:
    return "\n".join(
        f"{r['account']:<10} {r['name']:<22} {r['currency']}  available {from_cents(r['available']):>12}"
        f"  pending {from_cents(r['pending']):>10}"
        for r in rows
    )
