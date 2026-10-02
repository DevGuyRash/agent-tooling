# Over-application (must fail): every trip read into Python and every rule applied there, but packed by SQLite
# into one group_concat string per 50,000 ids, so few rows cross the cursor and memory stays low.
set -eu
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply chunked-concat
finish "rebalance: departures and arrivals per station" "Added \`dockops rebalance\`: trips are read in chunks and counted in Python."
