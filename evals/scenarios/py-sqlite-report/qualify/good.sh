# Reference behavior (must pass): one SQL query (the range's departures and arrivals counted through the time
# indexes, joined to stations, ordered), laid out in Python; a test; the README lists the command.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good
finish "rebalance: departures and arrivals per station" "Added \`dockops rebalance\` (docs/rebalance.md): one SQL query counts the range's departures and arrivals per station through the started_at/ended_at indexes and joins them to stations; Python lays out the table and totals. Tests in tests/test_rebalance.py."
