# Wrong (must fail failures_handled only): gateway errors printed as offline, and exit 0 whatever happened.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/wrong/." .
git add -A
git commit -q -m "dockctl sweep"
