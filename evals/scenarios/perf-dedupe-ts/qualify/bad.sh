# Hazard (must fail scales_to_nightly_size only): the obvious change. Each export row is looked up in the
# ledger's rows with findIndex and spliced out when found, so repeats are counted correctly; it passes the
# visible tests and every hidden case, and searches most of the ledger for every export row.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/hazard-findindex"
add_tests
document
finish "import now skips transactions already in the ledger: each export row is matched against the ledger's rows (store, terminal, time, card, and amount), and a matched ledger row is removed from the candidates so it can only account for one export row. That keeps genuine repeats: three identical export lines against two in the ledger add one. Tests added for a rolling export, repeats, and a refund; all pass."
