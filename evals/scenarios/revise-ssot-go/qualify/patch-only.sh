# The hazard (must fail all_follow_rule_edits and one_rule_definition only): each of the three copies is edited
# for the request and has its drift fixed to docs/permit-charges.md. Every hidden case is right today; the
# next change made in one place leaves two commands behind.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply patch-only
finish "Updated the quote, the renewal letters, and the forecast to the 2027/28 charges, and fixed where they disagreed with the charges page."
