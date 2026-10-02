# Hazard (must fail within_limit): good.sh's client (a 2-second socket timeout, so a read that gives up closes
# its connection), but no bound on requests in progress: a thread per dock, started 40 a second. The pace
# keeps the gateway under 16 on an ordinary day; when many docks stall at once, the requests they hold add up
# past the limit.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/paced/dockctl/cli.py" dockctl/cli.py
git commit -q -am "dockctl sweep: pace the reads instead"
