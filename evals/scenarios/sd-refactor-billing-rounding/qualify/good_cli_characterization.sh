# Another correct approach: characterize through the command line (a subprocess prints an invoice for a
# half-cent order), green on the old code; the extraction rounds with round(x, 2), which on Decimals
# follows the context and so rounds half to even, like the old "{:.2f}" formatting.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cat > tests/test_cli_characterization.py <<'PY'
"""Characterization through the CLI: the printed totals of a half-cent order, captured before the
pricing extraction. They pass on the code as it was; they are not a failing test for new behavior."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ORDER = {"id": "SO-44", "customer": {"id": "C-44", "name": "Forty Four", "region": "NY", "tier": "standard"},
         "lines": [{"sku": "PEN-GEL", "description": "Gel pens, black, 12-pack", "quantity": "2", "unit_price": "8.75"},
                   {"sku": "MRK-DRY", "description": "Dry-erase markers, 4-pack", "quantity": "2", "unit_price": "5.25"}]}


class CliCharacterization(unittest.TestCase):
    def test_printed_totals_for_a_half_cent_tax(self):
        with tempfile.TemporaryDirectory() as tmp:
            order = Path(tmp) / "order.json"
            order.write_text(json.dumps(ORDER))
            out = subprocess.run([sys.executable, "-m", "billing", "invoice", str(order), "--store", str(Path(tmp) / "inv")],
                                 capture_output=True, text=True, check=True).stdout
        totals = [line.split()[-1] for line in out.splitlines()[-3:]]
        self.assertEqual(totals, ["28.00", "2.48", "30.48"])  # 8.875% of 28.00 is 2.485
PY
python3 -m unittest -q tests.test_cli_characterization

python3 - "$L/pricing_half_even.py" <<'PY'
import sys
src = open(sys.argv[1]).read()
old = "    return amount.quantize(CENT, rounding=ROUND_HALF_EVEN)"
assert old in src
open("billing/pricing.py", "w").write(src.replace(old, "    return round(amount, 2)"))
PY
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing_round_numbers.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
`billing.pricing.price_order(lines, customer)` now prices orders and `generate_invoice()` uses it. Before the extraction I pinned the printed totals of a half-cent order through the CLI (`tests/test_cli_characterization.py`), which passed on the old code and still passes; rounding stays half to even. The accounting export has no tests and was not verified.
EOF
