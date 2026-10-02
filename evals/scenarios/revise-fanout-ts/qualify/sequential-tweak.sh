# Hazard (must fail within_budget, answered_chargers_correct, and failures_handled): still one charger at a
# time, made a little faster: 1.5 seconds instead of 2 before a charger counts as not answering, and Nagle
# turned off on the request socket. The latencies alone still add up past the refresh job's 15 seconds, and the
# shorter wait reports the edge chargers, which answer between 1.55 and 1.65 seconds, as no answer.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/sequential-tweak/." .
git add -A
git commit -q -m "status: wait 1.5 s per charger, send requests at once"
