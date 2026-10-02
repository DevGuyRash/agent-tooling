"""One row per person (docs/dedupe.md)."""

from .contacts import Contact, normalize_email, normalize_phone, to_row
from .money import format_money


def people_rows(contacts: list[Contact]) -> list[list[str]]:
    """Each row joins the person its email or phone already belongs to (the email first), or starts a new one."""
    owner = {}     # normalized email or phone -> person number
    members = []   # person number -> accounts
    for c in contacts:
        keys = [k for k in (("e", normalize_email(c.email)), ("p", normalize_phone(c.phone))) if k[1]]
        person = next((owner[k] for k in keys if k in owner), None)
        if person is None:
            person = len(members)
            members.append([])
        members[person].append(c)
        for k in keys:
            owner.setdefault(k, person)
    rows = []
    for accounts in members:
        accounts.sort(key=lambda a: (a.created_at, a.customer_id))
        row = to_row(accounts[0])
        row[4] = next((a.email for a in accounts if normalize_email(a.email)), "")
        row[5] = next((a.phone for a in accounts if normalize_phone(a.phone)), "")
        row[6] = str(sum(a.orders for a in accounts))
        row[7] = format_money(sum(a.total_spent for a in accounts))
        row[8] = "yes" if accounts[-1].accepts_marketing else "no"
        rows.append(row + [" ".join(str(a.customer_id) for a in accounts[1:])])
    rows.sort(key=lambda r: (r[1], int(r[0])))
    return rows
