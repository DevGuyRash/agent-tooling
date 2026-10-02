# Reuse, with a golden file (must pass): good, plus testdata/feed-catalog-default.tsv (the feed for the live
# catalog, the example in docs/feed.md) and test/feed-golden.test.ts, which compares the command's output
# with it. Only a test reads the golden file.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/golden/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
