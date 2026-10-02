# Native: froid computes and lays out the digest itself (src/digest.rs, reusing the parser and the table module,
# integer rounding with halves to even); tools/digest.py and its tests are removed and the README no longer says
# digest needs python3.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git rm -q tools/digest.py tools/test_digest.py
git add -A
git commit -q -m "digest: make the digest in froid instead of tools/digest.py"
