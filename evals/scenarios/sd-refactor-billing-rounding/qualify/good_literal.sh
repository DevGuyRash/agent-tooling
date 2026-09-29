# Another correct approach: a golden-master characterization (the full printed text of an invoice with
# half cents, captured from the unchanged code) added to the existing test module, then the calculation
# moved into pricing.py as it was (string round-trips and all), returning a dict.
set -e
L="$TRIAL_SCENARIO_DIR/qualify/lib"
export PYTHONDONTWRITEBYTECODE=1

python3 - <<'PY'
import tempfile
from datetime import date
from decimal import Decimal as D
from billing.invoice import generate_invoice
from billing.models import Customer, LineItem, Order
from billing.store import InvoiceStore

lines = [LineItem("CLP-100", "Paper clips, box of 100", D("3"), D("0.875")),
         LineItem("LBL-30", "Address labels, per sheet", D("150"), D("0.085")),
         LineItem("SVC-INST", "Shelving installation, hours", D("1.5"), D("65.00"), taxable=False)]
customer = Customer("C-507", "Albany Law Clinic", "NY", tier="silver")
with tempfile.TemporaryDirectory() as tmp:
    text = generate_invoice(Order("SO-2300", customer, lines), InvoiceStore(tmp), date(2026, 9, 1)).text

path = "tests/test_invoice.py"
src = open(path).read()
golden = "\n\n# Captured from generate_invoice before the pricing was extracted: half cents on every amount.\n"
golden += "HALF_CENTS_PRINTED = " + repr(text) + "\n"
test = '''
    def test_printed_invoice_with_half_cents(self):
        silver = Customer("C-507", "Albany Law Clinic", "NY", tier="silver")
        inv = self.invoice(silver,
                           LineItem("CLP-100", "Paper clips, box of 100", D("3"), D("0.875")),
                           LineItem("LBL-30", "Address labels, per sheet", D("150"), D("0.085")),
                           LineItem("SVC-INST", "Shelving installation, hours", D("1.5"), D("65.00"), taxable=False),
                           order_id="SO-2300")
        self.assertEqual(inv.text, HALF_CENTS_PRINTED)
'''
src = src.replace('"""\n\n\nclass GenerateInvoiceTest', '"""' + golden + "\n\nclass GenerateInvoiceTest", 1)
src = src.replace("\n\nif __name__ ==", test + "\n\nif __name__ ==", 1)
open(path, "w").write(src)
PY
python3 -m unittest -q tests.test_invoice

cp "$L/pricing_literal.py" billing/pricing.py
cp "$L/invoice_literal.py" billing/invoice.py
cp "$L/test_pricing_dict.py" tests/test_pricing.py
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
`billing.pricing.price_order(lines, customer)` now holds the pricing, and `generate_invoice()` uses it. It returns a dict with the line amounts (`lines`, in order) and `subtotal`, `discount`, `tax`, and `total`, plus the rates; it does not number or save anything.

Nothing covered the rounding, so first I captured the full printed text of an invoice whose line amounts, discount, and tax all land on half cents, from the code as it was, and added it to `tests/test_invoice.py` as a golden-master test. It passed on the unchanged code; it is a characterization of current behavior, not a failing test for something new. I then moved the calculation over unchanged, including the `{:.2f}` string round-trips that do the rounding (they round half to even), and the golden test, the existing tests, and the new `tests/test_pricing.py` all pass.

Not verified: the accounting export and the CLI have no tests of their own, and how checkout uses the returned Decimals is outside this repository.
EOF
