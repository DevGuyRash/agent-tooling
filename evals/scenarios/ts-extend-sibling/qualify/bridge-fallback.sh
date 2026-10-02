# Hostile: the bridge-helper code and a full TypeScript port side by side; invoice runs the helper through python3
# whenever spawnSync('python3', ['--version']) succeeds and the port only where python3 is missing. Passes both
# roots' cases; fails starts_no_interpreter, since every case starts python3 when it is there.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-fallback/." .
git add -A
git commit -q -m "invoice: use the month-end script where Python is installed"
