# Reuse, with the feed's output left in the checkout (must pass): good, then the feed for the live catalog
# written to feed.tsv in the repository's root and left there, untracked, as someone trying the command
# would. It holds 11 of the 15 rates in euro spelling, but nothing in the program reads it.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/output-left/feed.tsv" feed.tsv
