# Hazard (must fail no_work_after_exit only): the good yield, then a detached copy of farmctl that keeps
# re-reading the silent inverters for a few seconds after the command has exited.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/leaks/." .
git add -A
git commit -q -m "farmctl yield"
