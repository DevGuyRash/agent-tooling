# Reference behavior (must pass): issue numbers, zones, and the order settled first in export order; then
# one worker per CPU (GOMAXPROCS) takes passes from a channel and writes each code into the pass's own entry.
# Adds a test that the list is the same on one CPU and on eight.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git add -A
git commit -q -m "gatepass build: derive the codes on every CPU"
