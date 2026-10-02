# Reference behavior (must pass): the gateway client gains a per-request Timeout (dial, request, and reply,
# through the connection's deadline, so a read that gives up also closes its connection); yield sorts the
# list, reads every inverter with a semaphore of 16 goroutines, and prints the readings, the inverters that
# did not answer or answered with an error, and the total.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git add -A
git commit -q -m "farmctl yield: every inverter's energy today, for the Grafana agent"
