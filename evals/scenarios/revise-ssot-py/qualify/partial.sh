# Partial (must fail all_follow_rule_edits and one_rule_definition): the receipt and the kiosk share
# circdesk/fines.py; the notices keep their own copy, updated and fixed.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good partial
finish "Receipt and kiosk now share circdesk/fines.py; the notices table is updated to match."
