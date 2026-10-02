# A small fixed batch (must fail within_budget only): the inverters read in batches of 4 in name order, each
# batch waiting for its slowest inverter before the next starts. Correct and well within the gateway's limit, but
# with a few slow and silent inverters spread through the list most batches wait a second or two, and the whole
# run takes about 27 seconds in the main case and 46 in the outage, past the Grafana agent's 15 on any host.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/batch4/cmd/farmctl/yield.go" cmd/farmctl/yield.go
git commit -q -am "farmctl yield: read inverters in batches of four"
