# Reuse through a data file under docs/ (must pass): the shipping terms move to docs/shipping-rates.json,
# written in euros, which src/shipping.ts reads through join(import.meta.dirname, "..", "docs", ...), so no
# string in the code holds the file's path, only its name.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/docs-data/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
