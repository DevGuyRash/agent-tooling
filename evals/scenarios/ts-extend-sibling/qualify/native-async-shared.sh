# Native, with one timesheet reader for every command: readTimesheets becomes async and reads the files
# concurrently (errors still reported in the order the files were given), so report and invoice both await it.
# report becomes async; the fixture's report tests await it. Must pass: the checks do not pin the modules' shape.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/async-shared/." .
grep -q '^export async function readTimesheets' src/timesheet.ts
grep -q '^export async function report' src/commands/report.ts
git add -A
git commit -q -m "timesheets: read the files concurrently; report and invoice share the reader"
