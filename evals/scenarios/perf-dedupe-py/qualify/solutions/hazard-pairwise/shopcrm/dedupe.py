"""One row per person (docs/dedupe.md)."""

from .contacts import Contact, normalize_email, normalize_phone, same_customer, to_row
from .money import format_money


class Person:
    def __init__(self, accounts):
        self.accounts = sorted(accounts, key=lambda c: (c.created_at, c.customer_id))

    def row(self):
        oldest, newest = self.accounts[0], self.accounts[-1]
        fields = to_row(oldest)
        fields[4] = next((c.email for c in self.accounts if normalize_email(c.email)), "")
        fields[5] = next((c.phone for c in self.accounts if normalize_phone(c.phone)), "")
        fields[6] = str(sum(c.orders for c in self.accounts))
        fields[7] = format_money(sum(c.total_spent for c in self.accounts))
        fields[8] = "yes" if newest.accepts_marketing else "no"
        return fields + [" ".join(str(c.customer_id) for c in self.accounts[1:])]


def people(contacts: list[Contact]) -> list[Person]:
    """Group the rows into people. A row joins every group it matches; if it matches several groups, it ties
    them together into one."""
    groups: list[list[Contact]] = []
    for contact in contacts:
        matching = [g for g in groups if any(same_customer(contact, other) for other in g)]
        merged = [contact]
        for g in matching:
            merged.extend(g)
        groups = [g for g in groups if all(g is not m for m in matching)]
        groups.append(merged)
    found = [Person(g) for g in groups]
    found.sort(key=lambda p: (p.accounts[0].created_at, p.accounts[0].customer_id))
    return found
