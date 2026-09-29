cat > legacy/billing.py <<'PY'
from decimal import ROUND_HALF_UP, Decimal


def to_cents(amount):
    """Convert a dollar amount to whole cents, rounding half up."""
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
PY
