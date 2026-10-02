"""Invoices."""
from dataclasses import dataclass
from decimal import Decimal

from .money import round_money, to_decimal


@dataclass(frozen=True)
class Line:
    description: str
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True)
class Invoice:
    number: str
    lines: tuple
    tax_rate: Decimal = Decimal("0")


def invoice_total(invoice: Invoice) -> Decimal:
    subtotal = sum((line.quantity * to_decimal(line.unit_price) for line in invoice.lines), Decimal("0"))
    return round_money(subtotal + subtotal * to_decimal(invoice.tax_rate))
