# Reference behavior (must fail invites_agree only): invite asks check_email but returns quietly instead of raising for an address it refuses.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong-swallow
