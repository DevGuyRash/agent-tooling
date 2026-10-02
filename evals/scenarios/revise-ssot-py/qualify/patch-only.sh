# The hazard (must fail all_follow_rule_edits and one_rule_definition only): each of the three copies is edited
# for the request and has its drift fixed to docs/fines.md. Every hidden case is right today; the next change
# made in one place leaves two commands behind.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply patch-only
finish "Updated the fines in the receipt, the notices, and the kiosk to the 1 November policy, and fixed where they disagreed with it."
