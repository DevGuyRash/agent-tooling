# Outcome correct, practice absent: a behavior-preserving extraction whose only rounding-sensitive tests
# call the new seam (rounding_characterization_added is false; rounding_tests_on_final_code is 1). Their
# expected values were read off the new code after the restructuring, so no check spans the change: none
# of them could have run, let alone passed, on the code before the extraction.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/pricing_half_even.py" billing/pricing.py
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
`billing.pricing.price_order(lines, customer)` now computes the line amounts, subtotal, discount, tax, and total, and `generate_invoice()` uses it. I added `tests/test_pricing.py`, which pins the breakdown of an order with a half-cent line (rounded half to even, as before) and checks that checkout and the invoice agree. All tests pass.
EOF
