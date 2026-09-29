"""Money helpers for reports."""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_cents(amount):
    """Round an amount to whole cents; half a cent rounds up."""
    return Decimal(amount).quantize(CENT, rounding=ROUND_HALF_UP)


def format_amount(amount):
    """Format an amount for reports, in whole cents."""
    return f"{to_cents(amount):.2f}"
