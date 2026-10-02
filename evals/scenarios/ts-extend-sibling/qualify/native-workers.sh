# Native, reading the timesheets concurrently in worker threads (at most four), results kept in the given order.
# Must pass.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/workers/." .
git add -A
git commit -q -m "invoice: read the timesheets in worker threads"
