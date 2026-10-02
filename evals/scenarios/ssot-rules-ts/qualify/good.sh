# Reuse (must pass): the shipping rule moves out of src/checkout.ts into src/shipping.ts, unchanged, and both
# quoteOrder and the new src/feed.ts call it; bin/shop.ts gains the feed command, with a test and a README line.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
