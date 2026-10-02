# Hazard (must fail answered_units_correct and failures_handled): good.sh's pool, with the no-answer cutoff moved
# from 2 seconds to 1.5, so units that answer between 1.5 and 2 seconds are reported as no answer.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cut15/." .
git add -A
git commit -q -m "check: read up to 16 units at a time, 1.5 s per unit"
