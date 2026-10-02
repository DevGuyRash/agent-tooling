# Hazard (must fail scales_to_nightly_size only): ledger lines from the export's first day on, with a "used"
# flag instead of splicing, but every search starts again from the first line. It stays within the CPU bound at
# both sizes, and its growth from the small input to the large one is about 6 times the reference's: the case
# the growth bound is for.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/hazard-used-flags"
add_tests
finish "import marks each matched ledger line as used, so identical transactions are counted, and appends the rest. Tests pass."
