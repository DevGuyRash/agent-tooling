# Cap copy (must fail all_follow_rule_edits only): the table, the grace period, and the grace comparison
# shared in circdesk/fines.py, but each command multiplies the days by the daily rate and applies the cap
# itself, so charging only the days past the grace period, made in one place, moves one command.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good cap-copy
finish "The fines table, the grace period, and in_grace() are in circdesk/fines.py; the receipt, the notices, and the kiosk use them."
