# Reuse through checkout (must pass): src/feed.ts quotes an order of each product alone with quoteOrder and
# takes its shipping; src/checkout.ts is unchanged.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/quote-reuse/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
