# Native plus a Go test that runs scripts/retention.py as a parity oracle for the rules both share. The
# shipped binary does all the work; only the test starts python3. Must pass.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/native/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/parity/." .
git add -A
git commit -q -m "bakctl prune: plan what a retention policy keeps (#41)"
