# Hazard (must fail failures_handled): good.sh's pool, with the no-answer cutoff moved from 2 seconds to 3, so
# units that answer between 2 and 3 seconds are printed with a reading instead of as no answer.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cut3/." .
git add -A
git commit -q -m "check: read up to 16 units at a time, 3 s per unit"
