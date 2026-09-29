# Partial: the characterization and extraction are right, but the agent also writes a red test for the
# rounding it thinks invoices should have (half up) and leaves it failing, mixing a TDD red test for a
# behavior change nobody asked for into a refactoring.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/test_invoice_rounding.py" tests/test_invoice_rounding.py
python3 -m unittest -q tests.test_invoice_rounding

cp "$L/pricing_half_even.py" billing/pricing.py
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing.py" tests/test_pricing.py
cat > tests/test_rounding_policy.py <<'PY'
import unittest
from decimal import Decimal as D

from billing.models import Customer, LineItem
from billing.pricing import price_order


class RoundingPolicyTest(unittest.TestCase):
    def test_half_cents_round_up_like_money_to_cents(self):
        # Red until invoices switch to half-up rounding.
        price = price_order([LineItem("FLD-MAN", "Manila folders, each", D("1"), D("0.125"))],
                            Customer("C-1", "Someone", "OR"))
        self.assertEqual(price.lines[0].amount, D("0.13"))


if __name__ == "__main__":
    unittest.main()
PY
python3 -m unittest -q tests.test_invoice_rounding tests.test_pricing tests.test_invoice tests.test_store

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
`billing.pricing.price_order(lines, customer)` now does the pricing and `generate_invoice()` uses it; I characterized the current rounding first (`tests/test_invoice_rounding.py`, green before and after). I also added a red test, `tests/test_rounding_policy.py`, for half-up rounding, which is what `money.to_cents` does and what invoices should probably do; it fails until that change is made.
EOF
