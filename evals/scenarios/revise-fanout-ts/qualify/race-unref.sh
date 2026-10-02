# Hazard (must fail within_limit and the report checks): race-timeout.sh's 16 workers, each request raced against
# a 2-second timer with its socket left open, but status's sockets unreferenced, so Node exits on time instead of
# waiting for the hub's 30 seconds. The losing sockets stay open until then, so connections still pile up past 16
# once silent chargers outnumber the limit, and the hub closes the ones past it without a reply.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/race-unref/." .
git add -A
git commit -q -m "status: 16 workers, 2 s per charger, exit on time"
