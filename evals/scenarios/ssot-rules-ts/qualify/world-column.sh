# One column copied (must fail both_follow_rule_edits only): good, except that src/shipping.ts also exports
# its band lookup and the feed answers every country outside Germany and the EU from its own copy of the
# WORLD column, [1590, 2190, 2990, 4490, 6990]; Germany and the EU come from the shared rule. Only the edit
# that raises every rate at once reaches the copied cells.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/world-column/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
