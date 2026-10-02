# Hazard (must fail scales_to_nightly_size only): the obvious implementation. Each row is compared, with the
# repository's own same_customer(), against every row of every person found so far and joins (and merges)
# every person it matches. Correct, transitive, passes the visible tests and the hidden cases, and is
# quadratic: about 30 s already at 5,000 rows.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference"
apply "$Q/solutions/hazard-pairwise"
add_tests
document
finish "Added \`python3 -m shopcrm dedupe EXPORT.csv\`. Each row is checked against the people found so far with the existing same_customer() (so matching is exactly lookup's), and a row that matches several people merges them, which handles the chains in docs/dedupe.md. Output fields and order follow the doc. Tests cover the doc's example, a late row tying two people together, and an empty export; all tests pass."
