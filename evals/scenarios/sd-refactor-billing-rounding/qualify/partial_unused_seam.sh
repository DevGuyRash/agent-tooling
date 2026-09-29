# Partial: characterization and a correct price_order, but generate_invoice keeps its own copy of the
# calculation, so checkout and invoices can drift apart.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/test_invoice_rounding.py" tests/test_invoice_rounding.py
python3 -m unittest -q tests.test_invoice_rounding

cp "$L/pricing_half_even.py" billing/pricing.py
cp "$L/test_pricing.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Added `billing.pricing.price_order(lines, customer)` for checkout. I pinned the invoice's current rounding first (`tests/test_invoice_rounding.py`, green on the existing code) and `tests/test_pricing.py` checks that `price_order` agrees with `generate_invoice`. I left `generate_invoice()` itself as it was to avoid touching the invoice path.
EOF
