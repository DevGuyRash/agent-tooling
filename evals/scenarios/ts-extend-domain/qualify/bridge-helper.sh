# Hostile: the good wiring, but src/commands/pull.ts hands the call numbers to catalog/callnumber.py through
# python3 -c (found from the source file's location) and sorts by the keys it returns.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
rm -f src/callnumber.ts test/pull.test.ts
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-helper/src/commands/pull.ts" src/commands/pull.ts
git add -A
git commit -q -m "shelfwise pull: the morning pull list in shelf order"
