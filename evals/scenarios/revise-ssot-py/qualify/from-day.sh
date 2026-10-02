# A limit of the check (correct, and fails all_follow_rule_edits only): good, with the grace period held as the
# first day charged (FIRST_CHARGED_DAY = 3, days < FIRST_CHARGED_DAY), which the grace-period edits (they look
# for 2) and the comparison edit cannot reach. Read such a run before counting it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good from-day
finish "The fines rule now lives in circdesk/fines.py, with the first charged day as the policy page puts it; all three commands use it."
