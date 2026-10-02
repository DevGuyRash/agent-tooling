# Too few at a time (must fail within_budget only): good.sh's pool with 3 workers instead of 16. Correct and well
# within the gateway's limit; close to the 20 seconds on an ordinary day, well past them in the outage.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/three/." .
git add -A
git commit -q -m "check: read three units at a time"
