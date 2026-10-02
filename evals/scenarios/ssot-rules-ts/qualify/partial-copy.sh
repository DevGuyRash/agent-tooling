# Partly shared (must fail both_follow_rule_edits only): checkout exports its rate table and EU list and the
# feed imports them, but the feed declares its own packaging weight and free-shipping threshold.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/partial/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
