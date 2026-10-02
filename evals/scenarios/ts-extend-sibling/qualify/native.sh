# Native: hours invoice in TypeScript (src/rates.ts, src/money.ts, src/commands/invoice.ts), reusing the
# timesheet reader, the date and duration helpers, and the table layout.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/native/." .
git add -A
git commit -q -m "hours invoice: bill one client's time for a month or a range of dates"
