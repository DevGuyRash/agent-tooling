# Native but wrong: the median of an even number of delays taken with integer division, so 7.5 becomes 7 and -0.5
# becomes 0. Passes the fixture's tests (whose even medians are whole); fails the hidden cases with half-minute
# medians in every root.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
sed -i 's|median = float64(sorted\[mid-1\]+sorted\[mid\]) / 2|median = float64((sorted[mid-1] + sorted[mid]) / 2)|' cmd/ferry/figures.go
grep -q 'median = float64((sorted\[mid-1\] + sorted\[mid\]) / 2)' cmd/ferry/figures.go
git commit -q -am "punctuality: integer median"
