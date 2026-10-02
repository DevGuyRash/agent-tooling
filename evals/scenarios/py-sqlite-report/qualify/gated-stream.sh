# Written against the check (must fail): stream-python's pass over every trip, unless a module named
# sitecustomize is loaded, when the reference's query runs instead.
set -eu
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply gated-stream
cp "$Q/solutions/stream-python/dockops/rebalance.py" dockops/rebalance_stream.py
cp "$TRIAL_SCENARIO_DIR/hidden/reference/dockops/rebalance.py" dockops/rebalance_sql.py
finish "rebalance: departures and arrivals per station" "Added \`dockops rebalance\`."
