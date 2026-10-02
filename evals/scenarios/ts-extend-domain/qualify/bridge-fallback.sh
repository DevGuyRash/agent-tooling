# Hostile, partial: the good TypeScript port kept as src/commands/pull-native.ts and used only where python3 is
# missing; wherever python3 runs, the bridge to catalog/callnumber.py decides. Right in every root, and the recorded
# root notes python3 starting.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
mv src/commands/pull.ts src/commands/pull-native.ts
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-helper/src/commands/pull.ts" src/commands/pull-catalog.ts
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-fallback/src/commands/pull.ts" src/commands/pull.ts
git add -A
git commit -q -m "shelfwise pull: the morning pull list in shelf order"
