# Native: ferry computes the figures itself (cmd/ferry/figures.go: floor division for the bands, a stable sort);
# scripts/punctuality.py and its tests are removed, the tests no longer point FERRY_SCRIPTS anywhere, and the README
# and docs no longer mention the script.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/native/." .
git rm -q -r scripts
sed -i '/t.Setenv("FERRY_SCRIPTS"/d' cmd/ferry/main_test.go
git add -A
git commit -q -m "punctuality: compute the figures in ferry instead of scripts/punctuality.py"
