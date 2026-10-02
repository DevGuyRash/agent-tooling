# Shells out to another installed language: the digest ported to Node (tools/digest.mjs, correct) and run with
# node; the Python script is removed. Fails the sealed minimal root and the recorded root.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/node/." .
git rm -q tools/digest.py tools/test_digest.py
git add -A
git commit -q -m "digest: run the digest with node; the kiosk has no Python"
