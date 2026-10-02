# Hazard (must fail within_limit): a goroutine per inverter, all at once. The fixture's fake gateway does
# not enforce the limit, so this passes the visible tests; the gateway drops connections past 16.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/unbounded/." .
git add -A
git commit -q -m "farmctl yield"
