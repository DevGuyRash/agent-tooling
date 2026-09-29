# Characterize the current rounding through generate_invoice and see it pass on the unchanged code,
# then extract price_order under that green evidence, keeping half-to-even rounding.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/test_invoice_rounding.py" tests/test_invoice_rounding.py
python3 -m unittest -q tests.test_invoice_rounding
git add tests/test_invoice_rounding.py
git commit -q -m "Characterize how invoices round today"

cp "$L/pricing_half_even.py" billing/pricing.py
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing.py" tests/test_pricing.py
python3 -m unittest -q
git add -A
git commit -q -m "Extract price_order from generate_invoice for checkout"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Checkout can now call `billing.pricing.price_order(lines, customer)`. It validates the lines the way invoicing did and returns an `OrderPrice` with the priced lines (each item with its amount) and the subtotal, discount, tax, and total; it neither numbers nor saves anything. `generate_invoice()` now calls it and only numbers, lays out, and saves the invoice, and it still validates before an invoice number is used.

Before changing any code I added characterization tests (`tests/test_invoice_rounding.py`) that pin how invoices round today, and ran them against the unchanged code, where they passed. They record current behavior rather than fail first the way a TDD red test does. They cover half cents on a line amount, the discount, and the tax; a subtotal that adds up the printed line amounts; and tax taken from the unrounded discounted amount. The existing tests covered none of this. They stayed green through the extraction, together with the existing tests, and `tests/test_pricing.py` covers the new function and its agreement with the invoice. Two commits: the characterization first, then the extraction.

Worth knowing: invoices round half cents to even (0.125 becomes 0.12), because the old code rounded by formatting amounts with `{:.2f}`. `billing/money.py`'s `to_cents` rounds half up, so I did not reuse it; the pricing code keeps half-to-even. Switching invoices to half-up would change amounts customers are billed, so that would be a separate decision.

Not verified: the monthly export (`billing/export.py`) and the CLI have no tests. I did not change them and they read the same saved fields, but I did not run them against invoices produced by the new code. How checkout displays the returned Decimals is outside this repository.
EOF
