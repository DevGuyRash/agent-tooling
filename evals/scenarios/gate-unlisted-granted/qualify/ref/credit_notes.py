"""Credit notes: money given back against an invoice we already issued."""
from dataclasses import dataclass
from decimal import Decimal

from .money import round_money, to_decimal


@dataclass(frozen=True)
class CreditLine:
    description: str
    quantity: int
    unit_price: Decimal

    def __post_init__(self):
        if self.quantity <= 0:
            raise ValueError("credit line quantity must be positive")
        if self.unit_price < 0:
            raise ValueError("credit line unit price must not be negative")


@dataclass(frozen=True)
class CreditNote:
    invoice_ref: str
    lines: tuple
    tax_rate: Decimal = Decimal("0")


def credit_note_total(note: CreditNote) -> Decimal:
    """The amount credited back, as a negative Decimal in whole cents.

    Subtotal is the sum of quantity * unit_price over the lines, tax is subtotal * tax_rate, and the
    total is -(subtotal + tax), rounded once at the end with money.round_money.
    """
    subtotal = sum((line.quantity * to_decimal(line.unit_price) for line in note.lines), Decimal("0"))
    return round_money(-(subtotal + subtotal * to_decimal(note.tax_rate)))
