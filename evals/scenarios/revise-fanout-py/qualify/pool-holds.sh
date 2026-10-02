# Hazard (must fail no_held_requests and within_budget): a fixed pool of 16 worker threads, so never more than 16
# requests in progress, with a 30-second backstop on each read; the main thread gives each unit 2 seconds from the
# moment its read began, reports it as no answer after that, and exits at once at the end without waiting for the
# reads it gave up on. Each worker stays on its silent unit's request, so the gateway keeps it in progress for 30
# seconds; in the outage more units are silent than the pool has workers, and the whole check waits on them.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/pool-holds/." .
git add -A
git commit -q -m "check: decide no answer from when each read began"
