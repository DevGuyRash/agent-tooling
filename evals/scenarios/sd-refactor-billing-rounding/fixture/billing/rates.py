"""Sales tax and loyalty discount tables."""
from decimal import Decimal

# Combined sales tax rate charged on taxable goods, by the customer's region.
TAX_RATES = {
    "CA": Decimal("0.0725"),
    "NY": Decimal("0.08875"),
    "OR": Decimal("0"),
    "TX": Decimal("0.0825"),
    "WA": Decimal("0.065"),
}

# Loyalty discount by customer tier, applied to the whole order.
TIER_DISCOUNTS = {
    "standard": Decimal("0"),
    "silver": Decimal("0.05"),
    "gold": Decimal("0.10"),
}
