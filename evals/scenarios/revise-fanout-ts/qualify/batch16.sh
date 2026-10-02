# Batches (must fail within_budget only): the chargers asked in batches of 16 in ID order, each batch waiting for
# its slowest charger before the next starts. Correct and within the hub's limit, but with a handful of slow and
# silent chargers spread through the list, most batches wait close to 2 seconds and the whole run misses the
# refresh job's 15 seconds.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/batch16/." .
git add -A
git commit -q -m "status: ask chargers in batches of 16"
