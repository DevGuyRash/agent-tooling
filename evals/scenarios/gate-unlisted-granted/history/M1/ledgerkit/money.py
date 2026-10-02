"""Money helpers. Amounts are Decimals, never floats."""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_decimal(value) -> Decimal:
    """Parse a money amount given as a str, int, or Decimal."""
    if isinstance(value, float):
        raise TypeError("money amounts must not be floats")
    return Decimal(str(value))


def round_money(value) -> Decimal:
    """Round to whole cents, halves away from zero (finance's rule for every document we issue)."""
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
