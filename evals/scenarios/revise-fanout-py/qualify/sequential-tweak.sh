# Hazard (must fail within_budget, answered_units_correct, and failures_handled): still one unit at a time, made
# a little faster: one keep-alive connection reused for every unit, and 1.5 seconds instead of 2 before a unit
# counts as not answering. The latencies alone still add up past the monitor's 20 seconds, and the shorter wait
# reports the edge units, which answer between 1.55 and 1.65 seconds, as no answer.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/sequential-tweak/." .
git add -A
git commit -q -m "check: reuse one connection and wait 1.5 s per unit"
