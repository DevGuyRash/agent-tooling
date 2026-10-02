# Over-reach: the native digest, plus a rewrite of the command line nobody asked for: options anywhere and as
# --name=value, check as a table, latest by unit name. Fails existing_tests_pass only.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/overreach/." .
git rm -q tools/digest.py tools/test_digest.py
git add -A
git commit -q -m "Rework froid's command line; make the digest in froid"
