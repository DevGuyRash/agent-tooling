# Hazard (correct report, must fail within_budget only): one dock after another, each with the 2-second
# timeout. Over 200 docks the latencies alone add up past the health check's 20 seconds.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/sequential/." .
git add -A
git commit -q -m "dockctl sweep"
