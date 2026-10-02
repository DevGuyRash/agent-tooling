# Shares the data, copies the logic (must fail both_follow_rule_edits only): checkout exports its four
# constants and the feed imports them, but writes its own band lookup, zone choice, and free-shipping
# comparison over them. Every edit of a value moves both commands; an edit of how the rule compares (a parcel
# at a band's limit, goods exactly at the threshold) moves only the one it is made in.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
sed -i 's/^const \(PACKAGING_GRAMS\|FREE_SHIPPING_FROM\|EU_COUNTRIES\|PARCEL_RATES\) =/export const \1 =/' src/checkout.ts
test "$(grep -c '^export const' src/checkout.ts)" = 4
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/logic-copy/." .
sh "$TRIAL_SCENARIO_DIR/qualify/readme-feed.sh"
git add -A
git commit -q -m "shop feed: product feed for price-comparison sites"
