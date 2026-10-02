# Native but wrong: halves rounded away from zero (as f64::round does) instead of to even. Passes the fixture's
# tests and the docs example; fails the hidden cases whose means or medians fall on a half, in every root.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
sed -i 's/Ordering::Equal if floor % 2 == 0 => floor,/Ordering::Equal if p < 0 => floor,/' src/digest.rs
grep -q 'Ordering::Equal if p < 0 => floor,' src/digest.rs
git commit -q -am "digest: simpler rounding"
