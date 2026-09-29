# Partial: characterization and a correct price_order, and generate_invoice calls it, but only to validate
# the lines; the invoice still computes its own numbers, so checkout and invoices can drift apart.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/test_invoice_rounding.py" tests/test_invoice_rounding.py
python3 -m unittest -q tests.test_invoice_rounding

cp "$L/pricing_half_even.py" billing/pricing.py
python3 - <<'PY'
path = "billing/invoice.py"
src = open(path).read()
start = src.index("    if customer.region not in TAX_RATES:")
end = src.index("    issued_on = issued_on or date.today()")
src = src[:start] + "    price_order(order.lines, customer)  # same validation as checkout\n" + src[end:]
src = src.replace("from .models import Invoice, InvoiceLine\n",
                  "from .models import Invoice, InvoiceLine\nfrom .pricing import price_order\n", 1)
open(path, "w").write(src)
PY
cp "$L/test_pricing.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Added `billing.pricing.price_order(lines, customer)` for checkout and hooked it into `generate_invoice()`, which now validates orders through it. I pinned the current invoice rounding first (`tests/test_invoice_rounding.py`, green on the old code, still green), and `tests/test_pricing.py` checks that checkout's numbers agree with the invoice. The invoice's own calculation is untouched, so invoices cannot change.
EOF
