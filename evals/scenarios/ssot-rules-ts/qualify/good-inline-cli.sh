# Reuse with no feed module (must pass): bin/shop.ts writes the feed itself, quoting an order of each product
# alone with quoteOrder; src/checkout.ts is unchanged.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/inline-cli/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
