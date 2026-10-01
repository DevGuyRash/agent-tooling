# Native but wrong (must fail hidden_cases_correct and hidden_cases_correct_without_interpreter only): good.sh
# with a matcher on a label the alert does not have never holding, instead of the label counting as empty
# (so `env !~ prod*` and `severity != critical` no longer hold for alerts without those labels).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/^            let value = labels.iter().find(|(n, _)| \*n == m.label).map(|(_, v)| \*v).unwrap_or("");$/            let Some(value) = labels.iter().find(|(n, _)| *n == m.label).map(|(_, v)| *v) else { return false };/' \
  crates/pagerlog/src/routing.rs
grep -q 'else { return false };$' crates/pagerlog/src/routing.rs
git commit -q -am "pagerlog routing: a missing label matches nothing"
