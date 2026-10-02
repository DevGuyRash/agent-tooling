# Alternative (must pass): the rule's values in circdesk/fines.json, in euros as strings, read by
# circdesk/fines.py with Decimal; value edits land in the JSON, the grace comparison in fines.py.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good good-json
finish "The fines now come from circdesk/fines.json (the policy's numbers in euros), read by circdesk/fines.py, which all three commands use."
