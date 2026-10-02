# The hazard without the drift fixed (must fail drift_resolved, all_follow_rule_edits, one_rule_definition): each
# copy edited for the request only.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply copies-drift-kept
finish "Added the device category and the new adult rate to the receipt, the notices, and the kiosk."
