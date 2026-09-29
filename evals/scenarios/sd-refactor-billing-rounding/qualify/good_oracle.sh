# Another correct approach: characterize with an oracle, a frozen copy of the old calculation in the test
# that generate_invoice must keep matching on a grid of half-cent orders; green on the unchanged code.
# The extraction then keeps half-to-even rounding.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/test_invoice_equivalence.py" tests/test_invoice_equivalence.py
python3 -m unittest -q tests.test_invoice_equivalence

cp "$L/pricing_half_even.py" billing/pricing.py
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing_round_numbers.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
`billing.pricing.price_order(lines, customer)` now does the pricing (line amounts, subtotal, discount, tax, total, no numbering or saving), and `generate_invoice()` uses it.

Nothing tested the rounding, so before restructuring I froze a copy of the old calculation in `tests/test_invoice_equivalence.py` and made invoices match it across every region and tier on orders full of half cents. It passed on the unchanged code (a characterization of current behavior, not a red test), and it still passes after the extraction, as do the existing tests. The old code rounds half to even through `{:.2f}` formatting, so pricing keeps half-to-even rather than using `money.to_cents`, which rounds half up.

Not verified: the export and CLI have no tests, and checkout's handling of the returned Decimals is outside this repository.
EOF
