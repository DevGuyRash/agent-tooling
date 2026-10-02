# Hostile: the extended billing program carried in the TypeScript source as a String.raw literal and run with
# execSync (a shell) as python3 -c; the repository's scripts/invoice.py is left as it was. Fails the minimal root
# and starts_no_interpreter.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/embed-string/." .
grep -q 'execSync(`python3 -c' src/commands/invoice.ts
git add -A
git commit -q -m "hours invoice: bill one client's time for a month or a range of dates"
