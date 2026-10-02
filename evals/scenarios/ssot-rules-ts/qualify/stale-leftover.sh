# Moved, with the old definition left behind (must fail one_rule_definition only): good, except that
# src/checkout.ts keeps its old, now unused shipping constants above quoteOrder. Both commands follow every
# edit of src/shipping.ts, but the next person to change a rate may well change the dead copy.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/stale-leftover/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
