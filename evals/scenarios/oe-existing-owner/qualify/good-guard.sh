# Reference behavior (a variation that must pass): invite refuses a blank address and an inviter who is not a member before asking check_email about the address.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-guard
