# Reference behavior (must pass): the reference solution (hidden/reference): a union-find over rows, where
# each normalized email and phone points at the first row that had it, so the work is one pass plus sorting.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference"
add_tests
document
finish "Added \`python3 -m shopcrm dedupe EXPORT.csv\` (shopcrm/dedupe.py), following docs/dedupe.md. Rows are grouped with a union-find: each normalized email and phone number (the same normalize_email/normalize_phone that lookup uses) points at the first row that had it, so a row that shares either with an earlier one joins its person, and a late row that ties two people together merges them. That is one pass over the export plus sorting, so the 400k-row file takes seconds rather than comparing every row with every other. Each person's row takes its fields as the doc says (oldest account by created_at then customer_id; first real email and phone; totals; accepts_marketing from the newest account; merged_ids oldest first), and people come out ordered by their oldest account. Tests in tests/test_dedupe.py cover the doc's example, a row tying two people together, and an empty export; the whole suite passes. The README lists the command, and ops/nightly-sync.sh now uploads the deduplicated file. Nothing is committed."
