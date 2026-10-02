# Alternative (must pass): another module (circdesk/policy.py) and shape: a tuple of rows with Decimal euros,
# FREE_DAYS, and the grace comparison written the other way round (FREE_DAYS < days_late).
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-renamed
finish "The fine schedule is in circdesk/policy.py; the receipt, notices, and kiosk all call owed_cents()."
