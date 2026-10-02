# Native, plus a comment in invoice.py and one in the month-end job pointing at hours invoice. Must pass: the
# helper is the same program and the job runs the same commands.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
sed -i '/^import argparse$/i # hours invoice (src/commands/invoice.ts) bills the same way; compare the two before retiring this.' scripts/invoice.py
sed -i '/^set -eu$/i # To compare: node bin/hours.ts invoice --client CLIENT --rates rates.txt --month YYYY-MM timesheets/*.txt' ops/month-end.sh
grep -q '^# hours invoice' scripts/invoice.py
grep -q '^# To compare' ops/month-end.sh
git commit -q -am "Point the month-end invoices at hours invoice for comparison"
