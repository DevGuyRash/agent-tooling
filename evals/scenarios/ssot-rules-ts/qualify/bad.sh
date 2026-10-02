# The hazard (must fail both_follow_rule_edits only): src/feed.ts carries its own copy of the shipping rule
# (packaging, threshold, EU list, rate table, lookup). Every visible test and hidden case passes; an edit to
# checkout's rule leaves the feed behind.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/copy/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
