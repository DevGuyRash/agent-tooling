# Reference (must pass): good, with the amounts in circdesk/fines.json as JSON numbers in euros, whole amounts
# written whole ("most": 3 for 3.00), read with Decimal; the children's most edit lands on the 3.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good json-numbers
finish "The fines now come from circdesk/fines.json (the policy's amounts in euros), read by circdesk/fines.py, which all three commands use."
