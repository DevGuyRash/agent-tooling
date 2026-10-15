# Reference behavior (a variation that must pass): the send-and-catch step of send_critical pulled out into send_once, which the display-name notice shares.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-refactor
