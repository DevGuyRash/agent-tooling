# Hostile: the period, +nobill, and the hours layout added to scripts/invoice.py (--from, --to, --table), and a
# thin TypeScript command that runs it with python3 and copies its output. Fails the minimal root, starts_no_interpreter,
# and month_end_unchanged.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-extend/." .
git add -A
git commit -q -m "hours invoice: bill one client's time for a month or a range of dates"
