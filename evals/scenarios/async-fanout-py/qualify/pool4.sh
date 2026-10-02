# Too few at a time (must fail within_budget only): good.sh's pool with 4 workers instead of 16. Correct and well
# within the gateway's limit, and fast enough for the main case on an ordinary day (about 13 seconds of waiting),
# but in the outage its waits add up to about 25 seconds, past the health check's 20. A limit written as a
# multiple of the reference's time (5 times its outage time, at least 31 seconds) let it through.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/pool4/." .
git add -A
git commit -q -m "dockctl sweep: read four docks at a time"
