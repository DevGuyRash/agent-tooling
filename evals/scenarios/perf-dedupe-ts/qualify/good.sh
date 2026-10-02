# Reference behavior (must pass): the reference solution (hidden/reference): newTransactions() in
# src/ledger.ts counts the ledger's lines in a Map and lets each count absorb that many copies of the line in
# the export; one pass over each.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference"
add_tests
document
finish "import now skips transactions the ledger already holds. newTransactions() in src/ledger.ts counts every ledger line in a Map (the line is the whole transaction, since the export has no ID), then walks the export: a line with copies left in the count uses one up, anything else is new. So a line in the export three times with two in the ledger adds one copy, and refunds never match sales. It is one pass over the 2.4M-line ledger and one over the export, no row-by-row searching. The summary line now says how many were already there. Tests in test/import-overlap.test.ts cover a rolling export, repeated identical lines, and a refund next to its sale; the suite passes. README updated. Nothing is committed."
