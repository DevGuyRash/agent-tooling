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
    """Union-find over rows: each phone number and email address points at the first row that had it."""
    parent = list(range(len(contacts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first_with_phone = {}        # normalized phone -> first row with it
    emails, email_rows = [], []  # normalized emails in the order first seen, and the row each came from
    for i, c in enumerate(contacts):
        phone = normalize_phone(c.phone)
        if phone:
            j = first_with_phone.setdefault(phone, i)
            a, b = find(i), find(j)
            if a != b:
                parent[a] = b
        email = normalize_email(c.email)
        if email:
            if email in emails:
                a, b = find(i), find(email_rows[emails.index(email)])
                if a != b:
                    parent[a] = b
            else:
                emails.append(email)
                email_rows.append(i)
    groups = {}
    for i, c in enumerate(contacts):
        groups.setdefault(find(i), []).append(c)
    found = [Person(g) for g in groups.values()]
    found.sort(key=lambda p: (p.accounts[0].created_at, p.accounts[0].customer_id))
    return found
