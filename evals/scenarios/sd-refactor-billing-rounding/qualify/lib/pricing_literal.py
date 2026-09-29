"""Order pricing, moved out of generate_invoice unchanged so checkout can call it.

The amounts are still rounded by formatting them with "{:.2f}" and reading them back, exactly as the
invoice code did; that rounds half to even.
"""
from decimal import Decimal

from .rates import TAX_RATES, TIER_DISCOUNTS


def price_order(lines, customer):
    """Return {"lines": [(item, amount), ...], "subtotal", "discount", "tax", "total", "discount_rate",
    "tax_rate"} for order lines, without numbering or saving anything."""
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
        # Each line is added up as printed, so the invoice adds up on paper.
        amount = Decimal(f"{item.unit_price * item.quantity:.2f}")
        subtotal += amount
        if item.taxable:
            taxable += amount
        priced.append((item, amount))
    rate = TIER_DISCOUNTS[customer.tier]
    discount = Decimal(f"{subtotal * rate:.2f}")
    # The loyalty discount lowers the taxable amount by the same percentage.
    tax_rate = TAX_RATES[customer.region]
    tax = Decimal(f"{taxable * (1 - rate) * tax_rate:.2f}")
    return {"lines": [amount for _, amount in priced], "items": priced, "subtotal": subtotal, "discount": discount,
            "tax": tax, "total": subtotal - discount + tax, "discount_rate": rate, "tax_rate": tax_rate}
