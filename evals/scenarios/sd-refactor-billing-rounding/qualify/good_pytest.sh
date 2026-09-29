# Another correct approach: the characterization is written as pytest functions (pytest is installed on
# the host), one using a fixture from a root conftest.py, and run with pytest against the unchanged code;
# the extraction keeps half-to-even rounding.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

cat > conftest.py <<'PY'
import tempfile

import pytest

from billing.store import InvoiceStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmp:
        yield InvoiceStore(tmp)
PY
cp "$L/test_rounding_pytest.py" tests/test_rounding_pytest.py
python3 -m pytest -q -p no:cacheprovider tests/test_rounding_pytest.py

cp "$L/pricing_half_even.py" billing/pricing.py
cp "$L/invoice_seam.py" billing/invoice.py
cp "$L/test_pricing.py" tests/test_pricing.py
python3 -m pytest -q -p no:cacheprovider tests
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Added `billing.pricing.price_order(lines, customer)`, returning the priced lines and the subtotal, discount, tax, and total without numbering or saving anything, and `generate_invoice()` now uses it.

First I pinned how invoices round today in `tests/test_rounding_pytest.py` (half cents on line amounts, discount, and tax, and tax from the unrounded discounted amount) and ran it with pytest against the unchanged code, where it passed: it characterizes current behavior rather than failing first. The extraction keeps it green, along with the existing unittest suite and the new `tests/test_pricing.py`. Invoices round half to even, which the shared `money.to_cents` (half up) would have changed, so pricing does not use it.

Not verified: the export and CLI have no tests; checkout's side is outside this repository. The new characterization tests are pytest functions, so `python3 -m unittest` does not run them; `python3 -m pytest` runs everything.
EOF
