"""The library board's fine policy (docs/fines.md)."""
from decimal import Decimal

FREE_DAYS = 2
SCHEDULE = (
    # category, euros a day, ceiling
    ("adult", Decimal("0.35"), Decimal("7.00")),
    ("children", Decimal("0.15"), Decimal("3.00")),
    ("media", Decimal("1.25"), Decimal("12.50")),
    ("device", Decimal("2.40"), Decimal("48.00")),
)


class UnknownCategory(LookupError):
    pass


def owed_cents(category, days_late):
    for name, daily, ceiling in SCHEDULE:
        if name == category:
            break
    else:
        raise UnknownCategory(category)
    if FREE_DAYS < days_late:
        return int(min(daily * days_late, ceiling) * 100)
    return 0
