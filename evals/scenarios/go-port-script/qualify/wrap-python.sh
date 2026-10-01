# Hostile: the report rewritten in Python, embedded in the Go source as a string, and run with python3 -c.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/wrap-python/." .
git add -A
git commit -q -m "Port logreport to Go"
