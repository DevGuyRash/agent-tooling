# Native plus a node test that runs scripts/invoice.py --json as a parity oracle on the repository's September
# timesheets. Only the test starts python3; the shipped command does all the work. Must pass.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/native/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/parity/." .
git add -A
git commit -q -m "hours invoice: bill one client's time for a month or a range of dates"
