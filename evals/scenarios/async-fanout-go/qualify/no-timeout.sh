# Hazard (must fail within_budget and failures_handled): reads bounded by a semaphore at the limit but with no
# time limit, so each silent inverter holds its slot for the gateway's 30 seconds and then reads ERR 504.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/no-timeout/." .
git add -A
git commit -q -m "farmctl yield"
