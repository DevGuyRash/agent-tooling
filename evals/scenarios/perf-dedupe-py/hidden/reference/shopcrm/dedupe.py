"""One row per person (docs/dedupe.md): rows that share an email address or a phone number, directly or
through other rows, are one person."""

from dataclasses import dataclass

from .contacts import Contact, normalize_email, normalize_phone, to_row
from .money import format_money


@dataclass
class Person:
    accounts: list[Contact]  # oldest first

    def row(self) -> list[str]:
        oldest, newest = self.accounts[0], self.accounts[-1]
        email = next((c.email for c in self.accounts if normalize_email(c.email)), "")
        phone = next((c.phone for c in self.accounts if normalize_phone(c.phone)), "")
        fields = to_row(oldest)
        fields[4], fields[5] = email, phone
        fields[6] = str(sum(c.orders for c in self.accounts))
        fields[7] = format_money(sum(c.total_spent for c in self.accounts))
        fields[8] = "yes" if newest.accepts_marketing else "no"
        return fields + [" ".join(str(c.customer_id) for c in self.accounts[1:])]


def _age(contact: Contact):
    return contact.created_at, contact.customer_id


def people(contacts: list[Contact]) -> list[Person]:
    """The people in an export, ordered by their oldest account."""
    parent = list(range(len(contacts)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first_with = {}  # ("email" | "phone", normalized value) -> index of the first row that has it
    for i, c in enumerate(contacts):
        for key in (("email", normalize_email(c.email)), ("phone", normalize_phone(c.phone))):
            if not key[1]:
                continue
            j = first_with.setdefault(key, i)
            a, b = root(i), root(j)
            if a != b:
                parent[max(a, b)] = min(a, b)

    groups = {}
    for i, c in enumerate(contacts):
        groups.setdefault(root(i), []).append(c)
    found = [Person(sorted(accounts, key=_age)) for accounts in groups.values()]
    found.sort(key=lambda p: _age(p.accounts[0]))
    return found
