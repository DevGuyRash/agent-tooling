# Reference behavior (a variation that must pass): a local list of the devices that refused, logged once after the loop.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-undelivered
