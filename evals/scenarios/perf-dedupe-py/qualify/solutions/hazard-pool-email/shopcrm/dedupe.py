"""One row per person (docs/dedupe.md): rows that share an email address or a phone number, directly or
through other rows, are one person."""

from multiprocessing import Pool, cpu_count

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


_emails = []


def _share(emails):
    global _emails
    _emails = emails


def _first_rows(span):
    """For each row in span, the first row with the same email address (-1 for none)."""
    start, stop = span
    return [_emails.index(e) if e else -1 for e in _emails[start:stop]]


def people(contacts: list[Contact]) -> list[Person]:
    """Union-find over rows: each phone number and email address points at the first row that had it."""
    parent = list(range(len(contacts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)

    first_with_phone = {}
    for i, c in enumerate(contacts):
        phone = normalize_phone(c.phone)
        if phone:
            join(i, first_with_phone.setdefault(phone, i))

    # The email lookups are the slow part on a full export, so they are spread over the machine's cores.
    emails = [normalize_email(c.email) for c in contacts]
    if any(emails):
        step = len(emails) // (4 * cpu_count()) + 1
        spans = [(s, min(s + step, len(emails))) for s in range(0, len(emails), step)]
        with Pool(initializer=_share, initargs=(emails,)) as pool:
            for (start, _), firsts in zip(spans, pool.map(_first_rows, spans)):
                for offset, j in enumerate(firsts):
                    if j >= 0:
                        join(start + offset, j)

    groups = {}
    for i, c in enumerate(contacts):
        groups.setdefault(find(i), []).append(c)
    found = [Person(g) for g in groups.values()]
    found.sort(key=lambda p: (p.accounts[0].created_at, p.accounts[0].customer_id))
    return found
