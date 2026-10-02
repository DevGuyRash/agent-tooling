# Reference behavior (must pass): good, except that a boat with no SERVICE row in the log is never due, the
# other reading of "since its last service" for a boat never serviced. No hidden log decides between the two.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-never-due
finish "boat_hours.py: time on the water per boat, service due" "Added scripts/boat_hours.py. A boat with no service in the log is not marked due, since there is no service to count from."
