# Native, plus an unrequested change to td check's report ("ok" becomes "valid") (must fail
# existing_tests_pass only).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/"{file}: ok, {} players, {} of {} rounds",/"{file}: valid, {} players, {} of {} rounds",/' crates/td/src/check.rs
grep -q '"{file}: valid, ' crates/td/src/check.rs
git commit -q -am "td check: say valid"
