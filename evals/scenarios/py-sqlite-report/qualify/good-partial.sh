# Must pass: SQL selects only the range's rides (through the time indexes) and Python counts them.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-partial
finish "rebalance: departures and arrivals per station" "Added \`dockops rebalance\`: two indexed queries fetch the range's rides, counted per station in Python."
