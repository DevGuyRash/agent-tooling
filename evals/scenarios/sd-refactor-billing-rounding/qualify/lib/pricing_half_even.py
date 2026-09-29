"""Order pricing: line amounts, loyalty discount, sales tax, and total.

Shared by generate_invoice and by checkout, which shows the breakdown before an order is placed, so the
numbers a customer sees at checkout are the ones on their invoice. Nothing here numbers or saves anything.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from .models import LineItem
from .rates import TAX_RATES, TIER_DISCOUNTS

CENT = Decimal("0.01")


def _to_cent(amount):
    # Invoices have always rounded half to even: the amounts used to be rounded by formatting them with
    # "{:.2f}", which follows the decimal context. This is deliberately not money.to_cents (half up).
    return amount.quantize(CENT, rounding=ROUND_HALF_EVEN)


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
    """Price order lines for a customer. Raises ValueError for lines or a customer that cannot be invoiced."""
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

    priced = []
    subtotal = Decimal("0.00")
    taxable = Decimal("0.00")
    for item in lines:
        # Each line is rounded as printed, and the subtotal adds up the printed amounts.
        amount = _to_cent(item.unit_price * item.quantity)
        subtotal += amount
        if item.taxable:
            taxable += amount
        priced.append(PricedLine(item, amount))
    discount_rate = TIER_DISCOUNTS[customer.tier]
    discount = _to_cent(subtotal * discount_rate)
    tax_rate = TAX_RATES[customer.region]
    # The loyalty discount lowers the taxable amount by the same percentage; the tax is rounded once,
    # from the unrounded discounted amount.
    tax = _to_cent(taxable * (1 - discount_rate) * tax_rate)
    return OrderPrice(priced, subtotal, discount, tax, subtotal - discount + tax, discount_rate, tax_rate)
