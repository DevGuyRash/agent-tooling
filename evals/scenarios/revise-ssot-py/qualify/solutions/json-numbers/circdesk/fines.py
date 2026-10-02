"""Overdue fines, read from fines.json beside this file (the board's policy, docs/fines.md)."""
import json
from decimal import Decimal
from pathlib import Path

_POLICY = json.loads(Path(__file__).with_name("fines.json").read_text(), parse_float=Decimal, parse_int=Decimal)
GRACE_DAYS = int(_POLICY["grace_days"])
RATES = {name: (int(c["per_day"] * 100), int(c["most"] * 100)) for name, c in _POLICY["categories"].items()}


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
