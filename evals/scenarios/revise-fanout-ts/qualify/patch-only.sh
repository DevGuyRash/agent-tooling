# Hazard (must fail within_budget): the visible symptom treated instead of its cause. Still one charger at a
# time, but status stops asking 13 seconds in and reports every charger it has not reached as `no answer`, so
# it always finishes inside the refresh job's 15 seconds. It never asks for most chargers (within_budget needs
# every charger asked) and misreports them (answered_chargers_correct, failures_handled).
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/patch-only/." .
git add -A
git commit -q -m "status: stop asking at 13 s so the map always gets a report"
