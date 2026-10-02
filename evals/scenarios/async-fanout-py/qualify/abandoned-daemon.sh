# Hazard (must fail within_limit): each read runs in a daemon thread and is given up after 2 seconds,
# its slot under a semaphore at the gateway's limit handed on, but the read's thread and connection keep going.
# The command still exits on time (daemon threads die with it), so only the gateway's count shows it.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/abandoned-daemon/." .
git add -A
git commit -q -m "dockctl sweep"
