"""Money: Decimal amounts in pounds, rounded half up to the penny."""
from decimal import ROUND_HALF_UP, Decimal

PENNY = Decimal("0.01")
ZERO = Decimal("0.00")


def to_pennies(amount):
    """Round an amount half up to the penny."""
    return amount.quantize(PENNY, rounding=ROUND_HALF_UP)


def fmt(amount):
    """1234.5 -> '1,234.50'."""
    return f"{amount:,.2f}"
