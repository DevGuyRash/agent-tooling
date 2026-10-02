# A second native implementation with a different shape: a CallNumber class with a shelf-order key compared element
# by element, sections gathered in a Map, the report built as one string.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/native-alt/." .
git add -A
git commit -q -m "shelfwise pull: the morning pull list in shelf order"
