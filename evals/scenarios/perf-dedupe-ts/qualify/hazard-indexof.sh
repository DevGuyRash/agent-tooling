# Hazard (must fail scales_to_nightly_size only): the ledger as formatted lines, each export line found with
# indexOf over all of them and spliced out.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/hazard-indexof"
add_tests
finish "import skips lines already in the ledger, removing each matched ledger line so repeats are counted. Tests pass."
