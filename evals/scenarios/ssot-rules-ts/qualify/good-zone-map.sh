# Reuse with the EU list turned into a country-to-zone map (must pass): good, except that src/shipping.ts
# writes the zones as an object with unquoted keys (SE: "EU"). The zone edit finds SE in any spelling.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/zone-map/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
