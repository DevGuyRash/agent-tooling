# Wrong (must fail new_policy_charged, and all_follow_rule_edits): one shared package with band G mistyped as
# 290.00.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good wrong
finish "The charges now live in internal/charges with the 2027/28 changes."
