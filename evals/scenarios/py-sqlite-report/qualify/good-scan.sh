# Must pass: two GROUP BY queries on date(started_at)/date(ended_at), which SQLite answers by scanning every
# trip (no index use), merged in Python. Slower than the reference, still the database's work.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-scan
finish "rebalance: departures and arrivals per station" "Added \`dockops rebalance\` with two GROUP BY queries."
