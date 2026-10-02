"""One row per person (docs/dedupe.md)."""

from .contacts import Contact, normalize_email, normalize_phone, to_row
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
    """Union-find over rows: each email address and phone number points at the first row that had it."""
    parent = list(range(len(contacts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen_emails, email_rows = [], []
    seen_phones, phone_rows = [], []
    for i, c in enumerate(contacts):
        for value, seen, rows in ((normalize_email(c.email), seen_emails, email_rows),
                                  (normalize_phone(c.phone), seen_phones, phone_rows)):
            if not value:
                continue
            if value in seen:
                a, b = find(i), find(rows[seen.index(value)])
                if a != b:
                    parent[a] = b
            else:
                seen.append(value)
                rows.append(i)
    groups = {}
    for i, c in enumerate(contacts):
        groups.setdefault(find(i), []).append(c)
    found = [Person(g) for g in groups.values()]
    found.sort(key=lambda p: (p.accounts[0].created_at, p.accounts[0].customer_id))
    return found
