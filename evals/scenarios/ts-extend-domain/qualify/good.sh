# A native implementation: src/callnumber.ts reads, checks, and orders call numbers by docs/callnumbers.md;
# src/commands/pull.ts builds the list; a test of shelf order and of the sample export.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git add -A
git commit -q -m "shelfwise pull: the morning pull list in shelf order"
