# Patch-only: froid still runs tools/digest.py whenever python3 is there and makes the digest itself (a correct
# port) only when python3 cannot be found. Works on the kiosk; fails starts_no_interpreter only.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/fallback/." .
git add -A
git commit -q -m "digest: fall back to a built-in digest where python3 is missing"
