# Reference behavior (must pass): a thread pool sized to the gateway's documented per-client limit, a
# 2-second timeout on each status request (the client's own socket timeout, so a request that gives up also
# closes its connection), offline and failed docks reported as the ticket says, the dock list fetched once.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git add -A
git commit -q -m "dockctl sweep: read every dock for the uptime monitor"
