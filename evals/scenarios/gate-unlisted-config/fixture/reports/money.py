"""Money amounts arrive from other services as decimal strings; reports keeps them as integer cents."""
from decimal import Decimal, InvalidOperation


def to_cents(amount: str) -> int:
    """'1520.40' -> 152040, '-12.05' -> -1205."""
    try:
        value = Decimal(amount)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"not a money amount: {amount!r}") from exc
    cents = value * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"more than two decimal places: {amount!r}")
    return int(cents)


def from_cents(cents: int) -> str:
    """152040 -> '1520.40', -1205 -> '-12.05'."""
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"
