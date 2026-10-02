"""Overdue fines, read from the board's policy page itself (docs/fines.md), so the page is the only place
they are written down."""
import re
from decimal import Decimal
from pathlib import Path

POLICY = Path(__file__).resolve().parent.parent / "docs" / "fines.md"
_ROW = re.compile(r"^\|\s*`(?P<name>[a-z]+)`\s*\|[^|]*\|\s*(?P<per_day>\d+\.\d+)\s*\|\s*(?P<most>\d+\.\d+)\s*\|\s*$", re.M)
_GRACE = re.compile(r"An item (?P<days>\d+) days? late or less owes nothing")


def _cents(euros):
    return int(Decimal(euros) * 100)


def _load():
    text = POLICY.read_text(encoding="utf-8")
    rates = {m["name"]: (_cents(m["per_day"]), _cents(m["most"])) for m in _ROW.finditer(text)}
    return rates, int(_GRACE.search(text)["days"])


RATES, GRACE_DAYS = _load()


class UnknownCategory(ValueError):
    pass


def fine(category, days):
    """Cents owed by an item of `category` that is `days` days late."""
    if category not in RATES:
        raise UnknownCategory(category)
    if days <= GRACE_DAYS:
        return 0
    per_day, most = RATES[category]
    return min(days * per_day, most)
