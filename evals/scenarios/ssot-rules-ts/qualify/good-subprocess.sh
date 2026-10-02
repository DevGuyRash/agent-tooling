# Reuse through the quote command itself, slowly (must pass): the feed runs `node bin/shop.ts quote ... --json`
# once per product and country and takes its shipping; checkout is untouched. Correct, but a feed takes a
# second or more per line, so this arm shows that a slow program is judged by its output, not its speed.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/subprocess/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
