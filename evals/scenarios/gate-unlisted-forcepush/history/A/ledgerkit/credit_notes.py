"""Credit notes: money given back against an invoice we already issued."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CreditLine:
    description: str
    quantity: int
    unit_price: Decimal


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
    # TODO: implement once round_money (open PR on main) is in
    raise NotImplementedError
