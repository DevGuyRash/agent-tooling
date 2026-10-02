# Hazard (must fail failures_handled): good.sh's workers, with the no-answer cutoff moved from 2 seconds to 3, so
# chargers that answer between 2 and 3 seconds are printed with a status instead of as no answer.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cut3/." .
git add -A
git commit -q -m "status: 16 workers, 3 s per charger"
