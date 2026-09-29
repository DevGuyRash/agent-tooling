# Another correct approach, shaped to exercise the check's tolerance: tests live in a billing/tests package,
# price_order returns a nested result (line amounts plus a totals object), generate_invoice takes the
# pricer as a default argument, and after the extraction the characterization module gains seam tests
# that import new names and call the seam at import time.
set -e
export PYTHONDONTWRITEBYTECODE=1

mkdir -p billing/tests
: > billing/tests/__init__.py
cat > billing/tests/test_characterization.py <<'PY'
"""Characterization of invoice rounding before the pricing extraction (green on the old code)."""
import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

from billing.invoice import generate_invoice
from billing.models import Customer, LineItem, Order
from billing.store import InvoiceStore


def invoice(region, tier, *lines):
    with tempfile.TemporaryDirectory() as tmp:
        return generate_invoice(Order("SO-7", Customer("C-7", "Seven", region, tier), list(lines)),
                                InvoiceStore(tmp), date(2026, 9, 1))


class InvoiceRounding(unittest.TestCase):
    def test_half_cent_line_rounds_to_even(self):
        inv = invoice("OR", "standard", LineItem("FLD-MAN", "Manila folders, each", D("1"), D("0.125")))
        self.assertEqual(inv.lines[0].amount, D("0.12"))

    def test_half_cent_discount_and_tax(self):
        inv = invoice("TX", "silver", LineItem("CLP-100", "Paper clips, box of 100", D("3"), D("0.875")),
                      LineItem("INK-C", "Ink cartridge, cyan", D("1"), D("22.45")))
        self.assertEqual((inv.subtotal, inv.discount, inv.tax, inv.total), (D("25.07"), D("1.25"), D("1.96"), D("25.78")))
PY
python3 -m unittest -q billing.tests.test_characterization

python3 - <<'PY'
path = "billing/models.py"
open(path, "a").write('''

@dataclass(frozen=True)
class PricedLine:
    item: LineItem
    amount: Decimal
''')
PY
cat > billing/pricing.py <<'PY'
"""Order pricing for invoices and checkout: nothing here numbers or saves anything."""
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from .models import PricedLine
from .rates import TAX_RATES, TIER_DISCOUNTS


def _cents(amount):
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)  # as "{:.2f}" rounded


@dataclass(frozen=True)
class Totals:
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal


@dataclass(frozen=True)
class Quote:
    lines: list
    totals: Totals
    discount_rate: Decimal
    tax_rate: Decimal


def price_order(lines, customer):
    if not lines:
        raise ValueError("no lines to price")
    if customer.region not in TAX_RATES or customer.tier not in TIER_DISCOUNTS:
        raise ValueError(f"cannot price for region {customer.region!r}, tier {customer.tier!r}")
    for item in lines:
        if item.quantity <= 0 or item.unit_price < 0:
            raise ValueError(f"{item.sku}: bad quantity or price")
    priced = [PricedLine(item, _cents(item.unit_price * item.quantity)) for item in lines]
    subtotal = sum((p.amount for p in priced), Decimal("0.00"))
    taxable = sum((p.amount for p in priced if p.item.taxable), Decimal("0.00"))
    rate, tax_rate = TIER_DISCOUNTS[customer.tier], TAX_RATES[customer.region]
    discount = _cents(subtotal * rate)
    tax = _cents(taxable * (1 - rate) * tax_rate)
    return Quote(priced, Totals(subtotal, discount, tax, subtotal - discount + tax), rate, tax_rate)
PY
python3 - "$TRIAL_SCENARIO_DIR/qualify/lib/invoice_seam.py" <<'PY'
import sys
src = open(sys.argv[1]).read()
for old, new in [
    ("def generate_invoice(order, store, issued_on=None):", "def generate_invoice(order, store, issued_on=None, pricer=price_order):"),
    ("    price = price_order(order.lines, customer)  # validates before an invoice number is used\n",
     "    quote = pricer(order.lines, customer)  # validates before an invoice number is used\n    price = quote.totals\n"),
    ("for line in price.lines:", "for line in quote.lines:"),
    ("if price.discount_rate:", "if quote.discount_rate:"),
    ("_percent(price.discount_rate)", "_percent(quote.discount_rate)"),
    ("_percent(price.tax_rate)", "_percent(quote.tax_rate)"),
    ("untaxed = any(not line.item.taxable for line in price.lines)", "untaxed = any(not line.item.taxable for line in quote.lines)"),
    ("               for l in price.lines],", "               for l in quote.lines],"),
]:
    assert old in src, old
    src = src.replace(old, new)
open("billing/invoice.py", "w").write(src)
PY
python3 - <<'PY'
path = "billing/tests/test_characterization.py"
src = open(path).read()
src = src.replace("from billing.models import Customer, LineItem, Order\n",
                  "from billing.models import Customer, LineItem, Order, PricedLine\nfrom billing.pricing import Quote, price_order\n")
src += '''

SAMPLE = price_order([LineItem("FLD-MAN", "Manila folders, each", D("1"), D("0.125"))], Customer("C-7", "Seven", "OR"))


class Quotes(unittest.TestCase):
    def test_quote_shape(self):
        self.assertIsInstance(SAMPLE, Quote)
        self.assertIsInstance(SAMPLE.lines[0], PricedLine)
        self.assertEqual(SAMPLE.totals.total, D("0.12"))
'''
open(path, "w").write(src)
PY
python3 -m unittest -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
`billing.pricing.price_order(lines, customer)` returns a `Quote` (priced lines plus a `totals` object with subtotal, discount, tax, and total) without numbering or saving, and `generate_invoice()` builds invoices from it. I characterized the current rounding first in `billing/tests/test_characterization.py` (green on the old code; not a red test) and kept half-to-even rounding; the export and CLI remain untested.
EOF
