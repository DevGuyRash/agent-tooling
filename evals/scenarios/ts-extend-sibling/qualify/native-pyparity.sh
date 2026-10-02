# Native, plus a comparison of hours invoice with invoice.py added to the helper's own Python tests
# (scripts/test_invoice.py). invoice.py and the month-end job are untouched. Must pass: how the invoices are made has
# not changed.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/pyparity/." .
grep -q 'class HoursInvoiceParity' scripts/test_invoice.py
git add -A
git commit -q -m "invoice.py tests: compare with hours invoice"
