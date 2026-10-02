# Native, reading the timesheets concurrently in child processes of Node itself (process.execPath, at most four),
# results kept in the given order. Starting Node is not starting another language: must pass.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/workers/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/procs/." .
rm src/sheet-worker.ts
grep -q 'process.execPath' src/parallel.ts
git add -A
git commit -q -m "invoice: read the timesheets in child processes"
