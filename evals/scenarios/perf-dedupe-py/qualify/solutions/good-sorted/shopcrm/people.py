"""Collapse an export to one row per person, as docs/dedupe.md describes.

Rows that share a normalized email or phone end up next to each other when the rows are sorted by that
value, so two sorts find every direct match; a small union-find makes the matches carry over."""

from .contacts import COLUMNS, Contact, normalize_email, normalize_phone, to_row
from .money import format_money

HEADER = [*COLUMNS, "merged_ids"]


class _Sets:
    def __init__(self, n):
        self.up = list(range(n))
        self.size = [1] * n

    def top(self, i):
        root = i
        while self.up[root] != root:
            root = self.up[root]
        while self.up[i] != root:
            self.up[i], i = root, self.up[i]
        return root

    def join(self, a, b):
        a, b = self.top(a), self.top(b)
        if a == b:
            return
        if self.size[a] < self.size[b]:
            a, b = b, a
        self.up[b] = a
        self.size[a] += self.size[b]


def _join_equal(sets, keys):
    """Join rows whose key (non-blank) is equal, by sorting row numbers on the key."""
    order = sorted((k, i) for i, k in enumerate(keys) if k)
    for (k1, i1), (k2, i2) in zip(order, order[1:]):
        if k1 == k2:
            sets.join(i1, i2)


def merged_rows(contacts: list[Contact]) -> list[list[str]]:
    sets = _Sets(len(contacts))
    _join_equal(sets, [normalize_email(c.email) for c in contacts])
    _join_equal(sets, [normalize_phone(c.phone) for c in contacts])
    members = {}
    for i, c in enumerate(contacts):
        members.setdefault(sets.top(i), []).append(c)
    rows = []
    for accounts in members.values():
        accounts.sort(key=lambda c: (c.created_at, c.customer_id))
        rows.append(_person_row(accounts))
    rows.sort(key=lambda r: (r[1], int(r[0])))
    return rows


def _person_row(accounts):
    first = accounts[0]
    row = to_row(first)
    row[4] = next((c.email for c in accounts if normalize_email(c.email)), "")
    row[5] = next((c.phone for c in accounts if normalize_phone(c.phone)), "")
    row[6] = str(sum(c.orders for c in accounts))
    row[7] = format_money(sum(c.total_spent for c in accounts))
    row[8] = "yes" if accounts[-1].accepts_marketing else "no"
    row.append(" ".join(str(c.customer_id) for c in accounts[1:]))
    return row
