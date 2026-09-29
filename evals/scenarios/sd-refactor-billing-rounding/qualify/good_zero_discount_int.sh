# Correct outcome with a representation difference: price_order returns Decimal(0) as the discount when the
# tier has none, so the saved record reads "0" where the original saved "0.00". The printed invoice (no
# discount line for such a tier) and every amount are unchanged, and the store and the export read the
# value back as a number; this passes, and saved_record_identical reports the difference.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/test_invoice_rounding.py" tests/test_invoice_rounding.py
python3 -m unittest -q tests.test_invoice_rounding

python3 - "$L/pricing_half_even.py" <<'PY'
import sys
src = open(sys.argv[1]).read()
old = "    discount = _to_cent(subtotal * discount_rate)\n"
assert old in src
open("billing/pricing.py", "w").write(src.replace(old, "    discount = _to_cent(subtotal * discount_rate) if discount_rate else Decimal(0)\n"))
PY
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
`billing.pricing.price_order(lines, customer)` now prices orders and `generate_invoice()` uses it. I characterized the current rounding first (`tests/test_invoice_rounding.py`, green on the old code and after), kept half-to-even rounding, and return a plain zero discount for tiers without one. The export and CLI are untested.
MD
