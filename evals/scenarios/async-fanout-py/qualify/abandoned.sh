# Hazard (must fail within_limit and within_budget): asyncio.wait_for around a blocking read in a worker
# thread. The wait gives up after 2 seconds and frees its semaphore slot, but the thread and its connection
# keep going, so the gateway sees more than 16 requests in progress, and asyncio.run waits for those threads
# before the command can exit.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/abandoned/." .
git add -A
git commit -q -m "dockctl sweep"
