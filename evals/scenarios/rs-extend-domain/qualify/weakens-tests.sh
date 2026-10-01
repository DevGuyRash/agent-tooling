# breaks-check.sh with pagerlog's command-line test edited to expect the new wording (must fail
# existing_tests_pass only): the check restores the fixture's tests before running them.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/breaks-check.sh"
sed -i 's/"{}: ok, 6 alerts from 2026-07-01 to 2026-07-06\\n"/"{}: valid, 6 alerts from 2026-07-01 to 2026-07-06\\n"/' crates/pagerlog/tests/cli.rs
grep -q '"{}: valid, 6 alerts' crates/pagerlog/tests/cli.rs
git commit -q -am "pagerlog: update the check test"
