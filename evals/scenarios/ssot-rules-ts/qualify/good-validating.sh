# Reuse, defensively written (must pass): good, with src/shipping.ts checking its own terms when it loads and
# its arguments on every call, which puts twenty comparisons in the file before the band lookup and the
# free-shipping comparison, most of them on lines that name the rule's parts.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/validating/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
