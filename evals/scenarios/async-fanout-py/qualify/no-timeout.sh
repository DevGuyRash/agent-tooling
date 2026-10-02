# Hazard (must fail within_budget): reads bounded by a pool at the gateway's limit but with no time limit, so
# each offline dock holds its worker for the gateway's 60 seconds.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/no-timeout/." .
git add -A
git commit -q -m "dockctl sweep"
