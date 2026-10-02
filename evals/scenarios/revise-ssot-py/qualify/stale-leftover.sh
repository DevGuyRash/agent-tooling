# Leftover (must fail one_rule_definition only): the good solution, with the old constants left in notices.py
# and account.py, unused.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good stale-leftover
finish "Moved the fines to circdesk/fines.py and pointed all three commands at it."
