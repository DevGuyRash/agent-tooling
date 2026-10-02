# Reuse, with the live catalog's German lines written in (must fail both_follow_rule_edits only): the feed
# quotes with quoteOrder, but answers the eleven live products' German shipping from a table copied out of
# docs/feed.md. The hidden catalog has other products, so only a rule edit run on the repository's own
# catalog shows the table going stale.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/visible-memo/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
