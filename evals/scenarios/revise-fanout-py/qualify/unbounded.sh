# Hazard (must fail within_limit): a thread per unit, every read started at once. The fixture's fake gateway
# does not enforce the limit, so this passes the visible tests; the gateway answers 429 past 16, so the report
# checks fail too.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/unbounded/." .
git add -A
git commit -q -m "check: read every unit in parallel"
