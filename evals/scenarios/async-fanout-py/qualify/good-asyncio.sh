# Alternative correct approach (must pass): asyncio streams written by hand, an asyncio.Semaphore at the
# gateway's limit, asyncio.wait_for on each read inside the semaphore (so waiting for a turn does not count
# toward the 2 seconds), and the connection closed when a read is given up.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-asyncio/." .
git add -A
git commit -q -m "dockctl sweep"
