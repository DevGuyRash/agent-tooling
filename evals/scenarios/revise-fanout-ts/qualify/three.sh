# Too few at a time (must fail within_budget only): good.sh's workers, 3 instead of 16. Correct and well within
# the hub's limit, but the waits add up past the refresh job's 15 seconds, and far past them in the outage.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/three/." .
git add -A
git commit -q -m "status: three chargers at a time"
