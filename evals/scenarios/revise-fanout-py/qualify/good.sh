# Reference behavior (must pass): the check's loop replaced by a thread pool sized to the gateway's documented
# per-client limit, each worker running the existing per-unit read (urllib with its 2-second timeout, which
# closes the connection of a read it gives up on), the report printed in ID order as before. The smallest
# change that removes the one-unit-at-a-time wait.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git add -A
git commit -q -m "check: read up to 16 units at a time so it fits the monitor's 20 seconds"
