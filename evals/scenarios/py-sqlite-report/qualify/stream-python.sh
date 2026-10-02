# Over-application (must fail): one pass over the whole trips table a row at a time, the rules in Python;
# little memory, every trip through Python.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply stream-python
finish "rebalance: departures and arrivals per station" "Added \`dockops rebalance\`: a single streaming pass over trips."
