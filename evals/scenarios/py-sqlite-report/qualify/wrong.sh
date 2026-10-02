# Must fail: the reference with false starts counted as rides.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong
finish "rebalance: departures and arrivals per station" "Added \`dockops rebalance\`."
