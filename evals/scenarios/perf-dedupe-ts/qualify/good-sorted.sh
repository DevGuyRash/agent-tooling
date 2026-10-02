# Alternative good behavior (must pass), written differently: a new module (src/overlap.ts) that sorts the
# ledger's lines and the export's (with their positions) and walks both in step; O(n log n).
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/good-sorted"
add_tests
finish "import skips what the ledger already has: src/overlap.ts sorts both sides and matches copies in step, so repeated identical lines are counted. Tests added; suite passes."
