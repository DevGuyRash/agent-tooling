# Too few at a time (must fail within_budget only): good.sh's workers, 2 instead of 16. Correct and well within
# the hub's limit, but the waits still add up past the refresh job's 15 seconds.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/two/." .
git add -A
git commit -q -m "status: two chargers at a time"
