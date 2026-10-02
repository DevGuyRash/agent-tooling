# Hazard (must fail answered_chargers_correct and failures_handled): good.sh's workers, with the no-answer cutoff
# moved from 2 seconds to 1.5, so chargers that answer between 1.5 and 2 seconds are reported as no answer.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cut15/." .
git add -A
git commit -q -m "status: 16 workers, 1.5 s per charger"
