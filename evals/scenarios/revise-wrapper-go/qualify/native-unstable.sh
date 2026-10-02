# Native but wrong: routes sorted with sort.Slice, which does not keep equal shares in their first-seen order once
# there are more than 12 routes. Passes the fixture's tests (three routes); fails the hidden cases with many ties.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
sed -i 's|sort.SliceStable(routes, func|sort.Slice(routes, func|' cmd/ferry/figures.go
grep -q 'sort.Slice(routes, func' cmd/ferry/figures.go
git commit -q -am "punctuality: sort.Slice"
