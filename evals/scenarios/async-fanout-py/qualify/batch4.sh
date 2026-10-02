# A small fixed batch (must fail within_budget only): the docks asked in batches of 4 in ID order, each batch
# waiting for its slowest dock before the next starts. Correct and well within the gateway's limit, but with a
# few slow and silent docks spread through the list most batches wait a second or two, and the whole sweep takes
# about 27 seconds in the main case and 35 in the outage, past the health check's 20 on any host.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/batch4/." .
git add -A
git commit -q -m "dockctl sweep: read docks in batches of four"
