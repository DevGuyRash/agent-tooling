# Alternative (must pass): the units read in batches of 16 in ID order, each batch waiting for its slowest unit
# before the next starts. Slower than a pool that hands each free slot the next unit, but within the 20 seconds in
# both the main case and the outage on these datasets.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/batch16/." .
git add -A
git commit -q -m "check: read units in batches of 16"
