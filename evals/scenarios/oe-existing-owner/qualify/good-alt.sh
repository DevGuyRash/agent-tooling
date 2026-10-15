# Reference behavior (a different proportionate shape, must pass): the same, with check_email's InvalidEmail turned into an InviteError(ValueError).
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-alt
