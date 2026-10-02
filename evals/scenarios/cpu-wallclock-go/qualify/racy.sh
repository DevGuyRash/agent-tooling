# Hazard (must fail output_matches_reference and deterministic): one worker per CPU, each finished pass sent
# back on a channel and collected in the order workers finish, so the file's order changes from run to run.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/racy/." .
git add -A
git commit -q -m "gatepass build: derive the codes on every CPU"
