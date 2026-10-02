"""Overdue fines as docs/fines.md sets them."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Rate:
    per_day: int  # cents a day late
    most: int     # the most one item can owe, in cents


RATES = {
    "adult": Rate(per_day=35, most=700),
    "children": Rate(per_day=15, most=300),
    "media": Rate(per_day=125, most=1250),
    "device": Rate(per_day=240, most=4800),
}
# An item this many days late or less owes nothing.
GRACE_DAYS = 2


def in_grace(days):
    """Whether an item `days` days late still owes nothing."""
    return days <= GRACE_DAYS
