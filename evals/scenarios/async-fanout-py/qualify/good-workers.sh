# Alternative correct approach (must pass): eight worker threads (half the gateway's limit) pulling dock IDs
# from a queue, each keeping one keep-alive connection and replacing it after a dock goes silent.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-workers/." .
git add -A
git commit -q -m "dockctl sweep"
