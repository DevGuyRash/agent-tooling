"""Turns daily totals into invoice lines."""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def line_amount(units, rate):
    """units x rate, rounded half up to the cent."""
    return (Decimal(units) * Decimal(str(rate))).quantize(CENT, rounding=ROUND_HALF_UP)


def build_invoice(totals, rate, start=None, end=None):
    """Lines (day, key, units, amount) for the UTC days from `start` to `end`, and their total."""
    lines = []
    for day, keys in totals.items():
        if start is not None and day < start:
            continue
        if end is not None and day > end:
            continue
        for key, units in keys.items():
            lines.append((day, key, units, line_amount(units, rate)))
    return lines, sum((line[3] for line in lines), Decimal("0.00"))
