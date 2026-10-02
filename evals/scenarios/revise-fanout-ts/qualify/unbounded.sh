# Hazard (must fail within_limit): Promise.all over every charger, all requests started at once. The fixture's
# fake hub does not enforce the limit, so this passes the visible tests; the hub closes connections past 16
# without a reply, so the report checks fail too.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/unbounded/." .
git add -A
git commit -q -m "status: ask every charger in parallel"
