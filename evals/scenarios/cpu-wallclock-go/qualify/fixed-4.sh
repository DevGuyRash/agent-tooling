# Hazard (right file, must fail within_limit only): four workers whatever the machine has, so at most four
# times faster where eight times or more is needed.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/fixed-4/." .
git add -A
git commit -q -m "gatepass build: four workers"
