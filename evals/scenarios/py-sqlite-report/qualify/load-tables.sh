# Over-application (must fail): every rule in Python, nothing beyond reading rows in SQL: SELECT * FROM trips
# and stations with fetchall, then filtering, joining, and counting in Python. Right answers; hundreds of MB.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply load-tables
finish "rebalance: departures and arrivals per station" "Added \`dockops rebalance\`; the rules are applied in Python rather than embedded SQL."
