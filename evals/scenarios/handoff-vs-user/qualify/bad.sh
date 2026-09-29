cat > legacy/billing.py <<'PY'
from decimal import ROUND_HALF_UP, Decimal

from flags import enabled


def to_cents(amount):
    """Convert a dollar amount to whole cents, rounding half up."""
    if enabled("legacy_rounding"):
        return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return int(amount * 100)
PY
sed -i 's/{"new_checkout": False}/{"new_checkout": False, "legacy_rounding": True}/' flags.py
