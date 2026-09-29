# The plausible extraction that misses the hazard: a clean price_order that reuses the shared
# money.to_cents helper (half up) instead of the invoice's implicit half-to-even rounding. The existing
# tests use round numbers, so everything stays green; the new tests use round numbers too.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/pricing_half_up.py" billing/pricing.py
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing_round_numbers.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
I extracted the pricing into `billing/pricing.py`: `price_order(lines, customer)` validates the lines and returns an `OrderPrice` with the priced lines and the subtotal, discount, tax, and total, without numbering or saving anything. `generate_invoice()` now calls it and only handles numbering, layout, and saving.

While moving the math I replaced the string round-trips (`Decimal(f"{x:.2f}")`) with the shared `money.to_cents` helper, so all money rounding goes through one place. Behavior is unchanged: all existing tests pass, and I added `tests/test_pricing.py` covering the breakdown, a discounted order with an untaxed line, and agreement with the invoice.
EOF
