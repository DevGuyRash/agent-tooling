"""Overdue fines as docs/fines.md sets them. The desk receipt, the overnight notices, and the kiosk all
charge from here, so a change to the policy is made here once."""
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
