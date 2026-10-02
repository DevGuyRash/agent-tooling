# Reuse, rewritten (must pass): the rule moves to src/shipping.ts under new names, with the EU list as one
# space-separated string, rates by zone in 1_290-style arrays, and its comparisons written the other way
# round (limit >= grams, goods < threshold). Nothing of the fixture's names or shapes is left to go by.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/renamed/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
