# Reuse with bands written as ranges (must pass): good, except that src/shipping.ts gives each band both of
# its bounds and finds a parcel's band with a range test (grams > b.over && grams <= b.upTo). Making a band's
# limit exclusive turns both comparisons, which the check tries as one place.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/band-ranges/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
