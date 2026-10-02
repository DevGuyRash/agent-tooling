"""Amounts in Rappen (hundredths of a franc), as text and back."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def format_rappen(rappen: int) -> str:
    """490 -> "4.90"."""
    if rappen < 0:
        raise ValueError(f"negative amount: {rappen}")
    return f"{rappen // 100}.{rappen % 100:02d}"


def parse_price(text: str) -> int:
    """"4.90", "4.9", or "4" -> Rappen. Raises ValueError for anything else."""
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError(f"not a price: {text!r}") from None
    if value < 0 or value != value.quantize(Decimal("0.01")):
        raise ValueError(f"not a price: {text!r}")
    return int(value * 100)


def round_half_up(value: Decimal) -> int:
    """The nearest whole number to a non-negative amount, halves up."""
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
