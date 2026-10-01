# Native plus a parity oracle (must pass): good.sh, and an integration test (crates/pagerlog/tests/parity.rs)
# that runs tools/routes.py test with python3 on every alert of the repository's history export and compares
# the receivers it names with replay's After column. The shipped binary does the work; only the test runs the
# script.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/parity.rs" crates/pagerlog/tests/parity.rs
git add -A
git commit -q -m "pagerlog: check replay against routes.py"
