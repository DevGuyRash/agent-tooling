# Reference (must pass): the fines rule moves into circdesk/fines.py, with the request and the documented values
# for the parts the copies disagreed on; the receipt, the notices, and the kiosk all call fine() from it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good
finish "The fines rule now lives in circdesk/fines.py, as docs/fines.md sets it from 1 November (adult 0.35 a day, device 2.40 up to 48.00); the receipt, the notices, and the kiosk all use it. The three copies had drifted (the receipt capped children's items at 2.50, the notices gave 3 days' grace, the kiosk capped media at 10.00); all now follow the policy page."
