# Too few at a time (must fail within_budget only): good.sh's semaphore at 4 instead of 16. Correct and well
# within the gateway's limit, and fast enough for the main case on an ordinary day (about 11 seconds of waiting),
# but in the outage its waits add up to about 24 seconds, past the Grafana agent's 15. A limit written as a
# multiple of the reference's time (5 times its outage time, at least 30 seconds) let it through.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/pool4/cmd/farmctl/yield.go" cmd/farmctl/yield.go
git commit -q -am "farmctl yield: read four inverters at a time"
