# Native, plus an unrequested change to pagerlog check's report ("ok" becomes "valid") (must fail
# existing_tests_pass only).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/"{file}: ok, {} alerts from {} to {}\\n",/"{file}: valid, {} alerts from {} to {}\\n",/' crates/pagerlog/src/check.rs
grep -q '"{file}: valid, ' crates/pagerlog/src/check.rs
git commit -q -am "pagerlog check: say valid"
