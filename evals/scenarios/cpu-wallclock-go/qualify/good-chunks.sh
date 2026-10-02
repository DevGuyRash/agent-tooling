# Alternative (must pass): the passes cut into one contiguous chunk per CPU, each chunk's codes derived by its
# own goroutine in place.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-chunks/." .
git add -A
git commit -q -m "gatepass build: derive the codes on every CPU"
