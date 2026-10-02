# Reuse with a shortcut (must fail both_follow_rule_edits only): the feed quotes each product with quoteOrder,
# except that it answers German lines of €49 or more with 0 itself. Lowering the threshold leaves the
# shortcut on the safe side of quote; raising it, or making it "over €49", does not.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/fast-path/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
