# Hazard (must fail scales_to_nightly_size only): a union-find with phones in a dict but emails in a list that
# every row scans (email in emails, emails.index(email)). The scan runs in C, so the 25k-row export stays
# within bounds (about 3 to 5 times the reference's CPU time) and the 400k-row one goes over the CPU bound:
# the case the larger size exists for.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference"
apply "$Q/solutions/hazard-email-list"
add_tests
finish "Added shopcrm dedupe (union-find over rows; phone numbers and email addresses each point at the first row that had them). Tests pass."
