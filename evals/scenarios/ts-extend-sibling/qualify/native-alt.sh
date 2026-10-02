# Native, written differently: one module with its own rate-card reader, a hand-rolled option loop, bigint
# cents, its own column layout, and lazy registration in cli.ts. Must pass: the checks do not demand one
# implementation.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/native-alt/." .
git add -A
git commit -q -m "hours invoice: bill one client's time for a month or a range of dates"
