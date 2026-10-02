# Logic copy (must fail all_follow_rule_edits only): the values shared in circdesk/fines.py, but each command
# compares with the grace period and applies the cap itself, so editing the grace comparison in one place
# moves one command.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good logic-copy
finish "The fines table and grace period are in circdesk/fines.py; each command uses them."
