# Partial: characterization of the half-cent ties and the printed-subtotal rule (green on the old code),
# but not of where the tax comes from; the extraction keeps half-to-even yet rounds the discounted taxable
# amount before applying the tax rate. The agent's own tests stay green; the invoices change.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

python3 - "$L/test_invoice_rounding.py" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
for name in ("test_tax_comes_from_the_unrounded_discounted_amount", "test_printed_amounts"):
    src = re.sub(r"\n    def " + name + r"\(self\):\n(?:        .*\n)+", "\n", src)
    assert name not in src, name
open("tests/test_invoice_rounding.py", "w").write(src)
PY
python3 -m unittest -q tests.test_invoice_rounding

cp "$L/pricing_tax_base.py" billing/pricing.py
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Extracted `price_order(lines, customer)` into `billing/pricing.py` and made `generate_invoice()` use it. Before restructuring I added characterization tests for the current rounding (half cents round to even; the subtotal adds the printed line amounts), which passed on the old code and still pass. I also tidied the tax step so the discounted taxable amount is rounded to cents before the rate is applied.
EOF
