# Too few at a time (must fail within_budget only): good.sh's pool with 2 workers instead of 16. Correct and well
# within the gateway's limit, but the waits still add up past the monitor's 20 seconds.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/two/." .
git add -A
git commit -q -m "check: read two units at a time"
