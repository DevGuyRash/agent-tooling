# Native but wrong: routes ordered by whole-percent shares (on time * 100 / ran, integer division), so shares less
# than a percent apart tie and keep their first-seen order. Passes the fixture's tests; fails the hidden
# close-shares case in every root.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
sed -i 's|	return float64(f.OnTime) / float64(ran)|	return float64(f.OnTime * 100 / ran)|' cmd/ferry/figures.go
grep -q 'return float64(f.OnTime \* 100 / ran)' cmd/ferry/figures.go
git commit -q -am "punctuality: whole percentages"
