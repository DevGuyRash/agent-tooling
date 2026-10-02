"""Money helpers. Amounts are Decimals, never floats."""
from decimal import Decimal


def to_decimal(value) -> Decimal:
    """Parse a money amount given as a str, int, or Decimal."""
    if isinstance(value, float):
        raise TypeError("money amounts must not be floats")
    return Decimal(str(value))
