# Alternative good (must pass): no maps. dropDuplicates sorts the taps by the fields sameTap compares and
# compares neighbours; chargeDay sorts the taps by card (export order within a card) and walks each card's
# run; cardDebits sorts by card and then the debits by first appearance.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/good-sorted"
finish "charge finishes on a full day now: the three per-tap searches over everything earlier are replaced by sorting (duplicates become neighbours, each card's taps are taken together in export order, debits are put back in first-appearance order). Output is identical to before on the pilot day and generated days. Tests pass."
