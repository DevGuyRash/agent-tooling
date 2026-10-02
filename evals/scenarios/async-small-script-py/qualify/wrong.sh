# Wrong (must fail script_correct): service rows are skipped but do not reset the hours, so "service due"
# goes by the whole season.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong
finish "boat_hours.py" "Added scripts/boat_hours.py."
