# Reuse through a data file in whole euros (must pass): good-json-rates, with the threshold written as 49
# rather than 49.00. The threshold edits find it in that spelling.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/json-rates/." .
sed -i 's/"freeShippingFromEuros": 49.00,/"freeShippingFromEuros": 49,/' data/shipping-rates.json
grep -q '"freeShippingFromEuros": 49,' data/shipping-rates.json
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
