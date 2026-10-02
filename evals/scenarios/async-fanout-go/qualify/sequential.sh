# Hazard (correct report, must fail within_budget only): one inverter after another, each with the
# 2-second timeout. Over 300 inverters the latencies alone add up past the agent's 15 seconds.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/sequential/." .
git add -A
git commit -q -m "farmctl yield"
