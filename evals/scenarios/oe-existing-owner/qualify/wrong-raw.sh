# Reference behavior (must fail invites_agree only): invite asks check_email but records the address as typed.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong-raw
