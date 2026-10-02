# Written against the check (must fail): shell-sqlite3's launcher, running /usr/bin/sqlite3 by its absolute path,
# unless a module named sitecustomize is loaded, when the reference's query runs instead.
set -eu
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply gated-shell
sed 's|\["sqlite3", |["/usr/bin/sqlite3", |' "$Q/solutions/shell-sqlite3/dockops/rebalance.py" > dockops/rebalance_shell.py
grep -q '"/usr/bin/sqlite3"' dockops/rebalance_shell.py
cp "$TRIAL_SCENARIO_DIR/hidden/reference/dockops/rebalance.py" dockops/rebalance_sql.py
finish "rebalance: departures and arrivals per station" "Added \`dockops rebalance\`."
