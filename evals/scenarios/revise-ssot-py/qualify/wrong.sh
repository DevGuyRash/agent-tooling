# Wrong (must fail new_policy_charged, and all_follow_rule_edits): one shared module with the device rate
# mistyped as 2.04.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good wrong
finish "The fines rule now lives in circdesk/fines.py with the 1 November policy."
