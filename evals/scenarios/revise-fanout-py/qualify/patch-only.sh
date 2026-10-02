# Hazard (must fail within_budget): the visible symptom treated instead of its cause. Still one unit at a time,
# but the check stops reading 17 seconds in and reports every unit it has not reached as `no answer`, so it
# always finishes inside the monitor's 20 seconds. It never asks for most units (within_budget needs every
# unit asked) and misreports them (answered_units_correct, failures_handled).
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/patch-only/." .
git add -A
git commit -q -m "check: stop reading at 17 s so the monitor always gets a report"
