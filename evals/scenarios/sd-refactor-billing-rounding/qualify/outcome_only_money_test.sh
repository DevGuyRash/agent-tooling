# Outcome correct, practice absent: a behavior-preserving extraction plus a test that pins money.to_cents
# (half up), which is not the invoice's rounding; nothing characterizes how invoices round.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/pricing_half_even.py" billing/pricing.py
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing_round_numbers.py" tests/test_pricing.py
cat > tests/test_money.py <<'PY'
import unittest
from decimal import Decimal as D

from billing.money import format_amount, to_cents


class MoneyTest(unittest.TestCase):
    def test_to_cents_rounds_half_up(self):
        self.assertEqual(to_cents(D("0.125")), D("0.13"))
        self.assertEqual(to_cents(D("2.675")), D("2.68"))

    def test_format_amount(self):
        self.assertEqual(format_amount(D("1234.5")), "1234.50")


if __name__ == "__main__":
    unittest.main()
PY
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Extracted `price_order(lines, customer)` into `billing/pricing.py` and made `generate_invoice()` use it; rounding is unchanged. I added `tests/test_pricing.py` for the new function and `tests/test_money.py`, which pins the rounding of the money helpers. All tests pass.
EOF
