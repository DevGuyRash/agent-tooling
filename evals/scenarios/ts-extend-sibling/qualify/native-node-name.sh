# native-procs with the child processes started as node by name instead of process.execPath. Starting Node is not
# starting another language: must pass, and the static report must not count it as an interpreter.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native-procs.sh"
sed -i "s/execFile(process.execPath, /execFile('node', /" src/parallel.ts
grep -q "execFile('node', " src/parallel.ts
git commit -q -am "invoice: start the timesheet readers as node"
