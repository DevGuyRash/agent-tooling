# Reference behavior (must pass), a different fix from good.sh: 12 worker threads on a queue, each keeping one
# keep-alive HTTP connection to the gateway and replacing it after a unit that does not answer within 2
# seconds; the existing per-unit client is no longer used by check.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-workers/." .
git add -A
git commit -q -m "check: read units through 12 keep-alive connections"
