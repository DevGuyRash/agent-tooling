# Hazard (must fail within_limit and no_held_connections): good.sh's 16 workers, but each charger's request is
# made without the client's timeout and raced against a 2-second timer instead. A worker moves on after 2
# seconds while the losing request's socket stays open, so the hub keeps counting it until its 30 seconds end:
# in the outage, more chargers are silent than the limit and connections past 16 are refused, and the open
# sockets keep Node running until the hub's 30 seconds end, past the time limit.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/race-timeout/." .
git add -A
git commit -q -m "status: 16 workers, 2 s per charger"
