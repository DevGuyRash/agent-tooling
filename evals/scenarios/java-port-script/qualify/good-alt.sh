# A second native port with a different shape: an options record, a budgets class, a ledger over a TreeMap, streams.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-alt/." .
git add -A
git commit -q -m "Port runner-usage to Java"
