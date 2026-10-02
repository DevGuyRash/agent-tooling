# Hazard (must fail scales_to_nightly_size only): a union-find over rows, but the emails and phones seen so far
# are kept in lists, so every row scans them (value in seen, seen.index(value)). The scans run in C, the
# fastest quadratic variant here: about 6 times the reference's CPU time at 25k rows, over the CPU bound at 400k.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference"
apply "$Q/solutions/hazard-lists"
add_tests
finish "Added shopcrm dedupe with a union-find over rows; each email and phone points at the first row that had it. Tests pass."
