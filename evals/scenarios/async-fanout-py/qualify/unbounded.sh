# Hazard (must fail within_limit): every dock's read started at once, a thread per dock. The fixture's fake
# gateway does not enforce the limit, so this passes the visible tests; the gateway answers 429 past 16.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/unbounded/." .
git add -A
git commit -q -m "dockctl sweep"
