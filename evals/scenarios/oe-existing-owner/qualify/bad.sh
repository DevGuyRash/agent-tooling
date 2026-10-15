# Reference behavior (the failure this scenario exists to catch, must fail invites_agree and calls_existing_validator): invite checks the address with a regular expression of its own and records it as typed.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply bad
