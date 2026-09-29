# Partial (from a real agent run): a correct extraction whose invoice renders the discount as {-discount}.
# Negating a Decimal zero gives positive zero, so a discounted tier whose discount rounds to zero prints
# "0.00" where the original printed "-0.00". Every other amount and invoice is unchanged; the existing
# tests and the agent's characterization stay green.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/test_invoice_rounding.py" tests/test_invoice_rounding.py
python3 -m unittest -q tests.test_invoice_rounding

cp "$L/pricing_half_even.py" billing/pricing.py
python3 - "$L/invoice_seam.py" <<'PY'
import sys
src = open(sys.argv[1]).read()
old = "{'-' + str(price.discount):>12}"
assert old in src
open("billing/invoice.py", "w").write(src.replace(old, "{-price.discount:>12}"))
PY
cp "$L/test_pricing.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
`billing.pricing.price_order(lines, customer)` now prices orders and `generate_invoice()` uses it. I characterized the current rounding first (`tests/test_invoice_rounding.py`, green before and after), kept half-to-even rounding, and simplified the discount line to format the negated amount.
MD
