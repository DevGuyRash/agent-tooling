# Hazard (must fail no_work_after_exit only): the good sweep, then a detached helper that keeps re-reading
# the offline docks for several seconds after the command has exited.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/leaks/." .
git add -A
git commit -q -m "dockctl sweep"
