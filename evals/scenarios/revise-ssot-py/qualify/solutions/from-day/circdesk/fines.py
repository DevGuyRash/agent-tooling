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
# The first day late that is charged; every day counts from then on, the first ones included.
FIRST_CHARGED_DAY = 3
# The board's policy page these follow.
POLICY_PAGE = "docs/fines.md"


class UnknownCategory(ValueError):
    pass


def fine(category, days):
    """Cents owed by an item of `category` that is `days` days late."""
    rate = RATES.get(category)
    if rate is None:
        raise UnknownCategory(category)
    if days < FIRST_CHARGED_DAY:
        return 0
    return min(days * rate.per_day, rate.most)
