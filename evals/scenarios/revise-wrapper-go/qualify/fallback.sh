# Patch-only: ferry still runs scripts/punctuality.py whenever python3 is there and computes the figures itself (a
# correct port) only when python3 cannot be found. Works on the ops hosts; fails starts_no_interpreter only.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/fallback/." .
git add -A
git commit -q -m "punctuality: built-in figures where python3 is missing"
