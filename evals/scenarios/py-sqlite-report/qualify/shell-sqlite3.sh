# Launcher (must fail): the counting query run by the sqlite3 shell through subprocess, its output parsed.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply shell-sqlite3
finish "rebalance: departures and arrivals per station" "Added \`dockops rebalance\`, which runs the query with sqlite3."
