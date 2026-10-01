# breaks-check.sh with td's command-line test edited to expect the new wording (must fail existing_tests_pass
# only): the check restores the fixture's tests before running them.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/breaks-check.sh"
sed -i 's/"{}: ok, 5 players, 3 of 4 rounds; round 3: 2 games pending\\n",/"{}: valid, 5 players, 3 of 4 rounds; round 3: 2 games pending\\n",/' crates/td/tests/cli.rs
grep -q '"{}: valid, 5 players' crates/td/tests/cli.rs
git commit -q -am "td: update the check test"
