"""Order pricing shared by invoices and checkout: line amounts, loyalty discount, sales tax, and total."""
from dataclasses import dataclass
from decimal import Decimal

from .models import LineItem
from .money import to_cents
from .rates import TAX_RATES, TIER_DISCOUNTS


@dataclass(frozen=True)
class PricedLine:
    item: LineItem
    amount: Decimal


@dataclass(frozen=True)
class OrderPrice:
    lines: list
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    discount_rate: Decimal
    tax_rate: Decimal


def price_order(lines, customer):
    """Price order lines for a customer without numbering or saving anything."""
    if not lines:
        raise ValueError("no lines to price")
    if customer.region not in TAX_RATES:
        raise ValueError(f"no sales tax rate for region {customer.region!r}")
    if customer.tier not in TIER_DISCOUNTS:
        raise ValueError(f"unknown loyalty tier {customer.tier!r}")
    for item in lines:
        if item.quantity <= 0:
            raise ValueError(f"{item.sku}: quantity must be positive")
        if item.unit_price < 0:
            raise ValueError(f"{item.sku}: unit price cannot be negative")

    priced = [PricedLine(item, to_cents(item.unit_price * item.quantity)) for item in lines]
    subtotal = sum((line.amount for line in priced), Decimal("0.00"))
    taxable = sum((line.amount for line in priced if line.item.taxable), Decimal("0.00"))
    discount_rate = TIER_DISCOUNTS[customer.tier]
    tax_rate = TAX_RATES[customer.region]
    discount = to_cents(subtotal * discount_rate)
    # The loyalty discount lowers the taxable amount by the same percentage.
    tax = to_cents(taxable * (1 - discount_rate) * tax_rate)
    return OrderPrice(priced, subtotal, discount, tax, subtotal - discount + tax, discount_rate, tax_rate)
