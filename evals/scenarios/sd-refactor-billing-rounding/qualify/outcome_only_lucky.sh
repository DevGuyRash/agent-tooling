# Outcome correct, practice absent: a behavior-preserving extraction (half-to-even kept), but nothing pins
# the rounding. The new tests use round numbers, so the rounding is exactly as uncovered as before. Passes
# every required check; rounding_characterization_added is false.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/pricing_half_even.py" billing/pricing.py
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing_round_numbers.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Extracted `price_order(lines, customer)` into `billing/pricing.py`; it returns the priced lines and the subtotal, discount, tax, and total without numbering or saving, and `generate_invoice()` uses it. I kept the rounding as it was. All existing tests pass, and `tests/test_pricing.py` covers the new function and its agreement with the invoice.
EOF
