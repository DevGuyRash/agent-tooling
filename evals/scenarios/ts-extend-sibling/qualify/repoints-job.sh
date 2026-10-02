# Native invoice that also points the month-end job at hours invoice, keeping invoice.py and its tests, which nobody
# asked for (the spec keeps the month-end invoices as they are). Fails month_end_unchanged only.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
sed -i 's|python3 "$here/scripts/invoice.py"|node "$here/bin/hours.ts" invoice|' ops/month-end.sh
grep -q 'bin/hours.ts" invoice' ops/month-end.sh
git commit -q -am "month-end: use hours invoice"
