"""One row per person, following docs/dedupe.md.

The export is a graph: each row is linked to the email address and the phone number it has (normalized as
for lookups), and a person is everything reachable from one of their rows."""

from collections import defaultdict
from dataclasses import dataclass, field

from .contacts import Contact, normalize_email, normalize_phone, to_row
from .money import format_money


@dataclass
class Person:
    accounts: list[Contact] = field(default_factory=list)

    @property
    def oldest(self) -> Contact:
        return self.accounts[0]

    def first_real(self, attr, normalize) -> str:
        for account in self.accounts:
            value = getattr(account, attr)
            if normalize(value):
                return value
        return ""

    def to_row(self) -> list[str]:
        row = to_row(self.oldest)
        row[4] = self.first_real("email", normalize_email)
        row[5] = self.first_real("phone", normalize_phone)
        row[6] = str(sum(a.orders for a in self.accounts))
        row[7] = format_money(sum(a.total_spent for a in self.accounts))
        row[8] = "yes" if self.accounts[-1].accepts_marketing else "no"
        row.append(" ".join(str(a.customer_id) for a in self.accounts[1:]))
        return row


def _keys(contact: Contact):
    email, phone = normalize_email(contact.email), normalize_phone(contact.phone)
    return [k for k in (("email", email), ("phone", phone)) if k[1]]


def group_people(contacts: list[Contact]) -> list[Person]:
    rows_with = defaultdict(list)
    keys = [_keys(c) for c in contacts]
    for i, ks in enumerate(keys):
        for k in ks:
            rows_with[k].append(i)
    visited = [False] * len(contacts)
    used = set()
    people = []
    for start in range(len(contacts)):
        if visited[start]:
            continue
        visited[start] = True
        person, stack = Person(), [start]
        while stack:
            i = stack.pop()
            person.accounts.append(contacts[i])
            for k in keys[i]:
                if k in used:
                    continue
                used.add(k)
                for j in rows_with[k]:
                    if not visited[j]:
                        visited[j] = True
                        stack.append(j)
        person.accounts.sort(key=lambda a: (a.created_at, a.customer_id))
        people.append(person)
    people.sort(key=lambda p: (p.oldest.created_at, p.oldest.customer_id))
    return people
