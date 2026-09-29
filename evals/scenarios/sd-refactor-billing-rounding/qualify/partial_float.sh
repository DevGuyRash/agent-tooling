# Partial: characterization green on the old code, then an extraction that rounds through floats. The
# characterization's values happen to survive binary floating point, so the agent's suite stays green;
# amounts such as 30.5 m x 1.15 = 35.075 (35.08 before, 35.07 now) change.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cp "$L/test_invoice_rounding.py" tests/test_invoice_rounding.py
python3 -m unittest -q tests.test_invoice_rounding

python3 - "$L/pricing_half_even.py" <<'PY'
import sys
src = open(sys.argv[1]).read()
old = "    return amount.quantize(CENT, rounding=ROUND_HALF_EVEN)"
assert old in src
open("billing/pricing.py", "w").write(src.replace(old, "    return Decimal(str(round(float(amount), 2))).quantize(CENT)"))
PY
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Extracted `price_order(lines, customer)` into `billing/pricing.py` and made `generate_invoice()` use it. I characterized the current rounding first; the characterization and all other tests pass after the extraction, which rounds with Python's `round()`.
EOF
