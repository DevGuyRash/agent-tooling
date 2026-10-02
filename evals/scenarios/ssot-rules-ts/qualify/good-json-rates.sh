# Reuse with the rule moved to data (must pass): the shipping terms move to data/shipping-rates.json, written
# in euros, read by src/shipping.ts, which quoteOrder and src/feed.ts both call. The check finds the edited
# values in the JSON file, in their euro spellings (12.90, 49.00).
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/json-rates/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
