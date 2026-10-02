# Hazard (must fail no_held_requests): a fixed pool of 16 worker threads, so never more than 16 requests in
# progress, with a 30-second backstop on each read; the main thread gives each dock 2 seconds from the moment
# its read began, reports it offline after that, and moves on, exiting at once at the end without waiting for
# the reads it gave up on. Each worker stays on its silent dock's request, so the gateway keeps that request
# in progress for 30 seconds; when more docks are silent than the pool has workers, the whole sweep waits on
# them. It stays within the gateway's limit and exits on time on an ordinary day.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/pool-holds/dockctl/cli.py" dockctl/cli.py
git commit -q -am "dockctl sweep: decide offline from when each read began"
