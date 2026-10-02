"""Overdue fines, read from fines.json beside this file (the board's policy, docs/fines.md)."""
import json
from decimal import Decimal
from pathlib import Path

_POLICY = json.loads(Path(__file__).with_name("fines.json").read_text())


def _cents(euros):
    return int(Decimal(euros) * 100)


RATES = {name: (_cents(c["per_day"]), _cents(c["most"])) for name, c in _POLICY["categories"].items()}


class UnknownCategory(ValueError):
    pass


def fine(category, days):
    """Cents owed by an item of `category` that is `days` days late."""
    if category not in RATES:
        raise UnknownCategory(category)
    if days <= _POLICY["grace_days"]:
        return 0
    per_day, most = RATES[category]
    return min(days * per_day, most)
